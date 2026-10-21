"""Protocol and connector boundaries use fictional fixtures and disposable storage."""
from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent_client import WorkspaceClient
from app.cli import main
from app.connectors import memoket
from app.database import store
from app.main import app


def test_local_client_rejects_remote_urls():
    for url in ('https://example.com', 'http://127.0.0.1.evil.test', 'http://u:p@localhost:8000', 'http://localhost:8000/api'):
        with pytest.raises(ValueError):
            WorkspaceClient(url)


def test_cli_creates_and_exports_via_http(monkeypatch, capsys, tmp_path):
    calls = []
    def respond(request):
        calls.append(request)
        assert request.headers['X-User-Id'] == 'fictional'
        return httpx.Response(200, json={'id': 'maple', 'title': 'Maple', 'content': 'A fictional draft.'})
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kw: real_client(**kw, transport=httpx.MockTransport(respond)))
    source = tmp_path / 'draft.md'
    source.write_text('A fictional draft.')
    assert main(['--user', 'fictional', 'create', '--title', 'Maple', '--file', str(source)]) == 0
    assert json.loads(capsys.readouterr().out)['id'] == 'maple'
    assert json.loads(calls[0].content)['content'] == source.read_text()
    assert main(['--user', 'fictional', 'export', 'maple']) == 0
    assert capsys.readouterr().out == '# Maple\n\nA fictional draft.\n'


def test_memoket_cli_has_no_shell_or_write_tools(monkeypatch):
    calls = []
    monkeypatch.setattr(memoket, 'executable', lambda: '/trusted/memoket')
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=b'{"conversation_ids":["1234567890123456789"]}')
    monkeypatch.setattr(memoket.subprocess, 'run', run)
    assert memoket.read('search_recordings', {'query': 'Maple; $(touch /tmp/no)'})['conversation_ids'][0] == '1234567890123456789'
    args, kwargs = calls[0]
    assert args[:4] == ['/trusted/memoket', 'call', 'search_recordings', '--json']
    assert json.loads(args[4])['query'].endswith('$(touch /tmp/no)')
    assert not kwargs.get('shell')
    with pytest.raises(memoket.ConnectorError):
        memoket.read('delete_recording', {})
    assert len(calls) == 1


def test_connector_diagnostics_do_not_expose_cli_output(monkeypatch):
    monkeypatch.setattr(memoket, 'executable', lambda: '/trusted/memoket')
    monkeypatch.setattr(memoket.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stderr=b'private secret', stdout=b'private content'))
    with pytest.raises(memoket.ConnectorError) as error:
        memoket.read('get_brief', {'conversation_ids': ['fictional']})
    assert 'private' not in str(error.value)


def test_import_is_incremental_and_user_scoped(monkeypatch):
    monkeypatch.setattr(memoket, 'read', lambda *a: {'items': [{'conversation_id': 'maple-1', 'body': 'A fictional Maple report.'}]})
    client = TestClient(app)
    payload = {'conversation_id': 'maple-1', 'title': 'Maple recording', 'to': 'notes'}
    for _ in range(2):
        response = client.post('/api/connectors/memoket/import', json=payload, headers={'X-User-Id': 'fictional'})
        assert response.status_code == 200
        items = store.get_items(response.json()['job_id'])
        assert items[0]['status'] == 'done'
    notes = store.list_notes('fictional')
    assert len(notes) == 1
    assert notes[0]['source'] == 'memoket'
    assert 'maple-1' in notes[0]['content']
    assert not store.list_notes('another-user')
    with store.connect() as db:
        db.execute("UPDATE notes SET updated_at='2099-01-01' WHERE id=?", (notes[0]['id'],))
    monkeypatch.setattr(memoket, 'read', lambda *a: {'body': 'Changed at source.'})
    client.post('/api/connectors/memoket/import', json=payload, headers={'X-User-Id': 'fictional'})
    assert 'A fictional Maple report.' in store.get_note('fictional', notes[0]['id'])['content']


def test_partial_or_empty_report_is_not_silently_imported(monkeypatch):
    for result in ({'items': []}, {'content': [{'type': 'text', 'text': '{"items": []}'}]},
                   {'body': 'Only the first page', 'next_offset': 1}):
        monkeypatch.setattr(memoket, 'read', lambda *a: result)
        with pytest.raises(memoket.ConnectorError):
            memoket.brief_snapshot('fictional')


@pytest.mark.asyncio
async def test_mcp_discovery_call_and_tool_annotations():
    from mcp import Client
    from app.mcp_server import create_server
    fake = SimpleNamespace(notes=lambda query: {'notes': [{'id': 'maple', 'title': query}], 'total': 1})
    async with Client(create_server(fake)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert tools['get_note'].annotations.read_only_hint is True
        assert tools['create_note'].annotations.read_only_hint is False
        assert tools['read_memoket'].annotations.open_world_hint is True
        assert 'delete_note' not in tools
        result = await client.call_tool('list_notes', {'query': 'Fictional Maple'})
        assert not result.is_error
        assert result.structured_content['notes'][0]['title'] == 'Fictional Maple'


def test_selected_revision_preserves_paragraph_boundaries(monkeypatch):
    from app.routers import compose
    async def complete(*args, **kwargs):
        return '{"text":"The rehearsal went well.","reason":"Grammar"}'
    monkeypatch.setattr(compose.llm, 'complete', complete)
    selection = '\n\nThe rehearsal went pretty good.\n\n'
    before = '# Maple' + selection + '## Next steps'
    response = TestClient(app).post('/api/rewrite', json={
        'content': before, 'selection': selection, 'intent': 'polish'})
    assert response.status_code == 200
    revision = response.json()['revisions'][0]
    after = before.replace(revision['anchor'], revision['text'])
    assert after == '# Maple\n\nThe rehearsal went well.\n\n## Next steps'


def test_block_preparation_does_not_request_final_prose():
    from app.harness import modes
    from app.harness.hooks.block import BlockHooks
    from app.harness.state import State
    from app.harness.tools import ToolContext
    state = State(mode=modes.EDA, ctx=ToolContext(user='fictional'), before='| Outcome | Readers |')
    hooks = BlockHooks(title='Fictional Maple')
    prepare = hooks._user(state, facts='', preparing=True)
    assert '[Preparation] Call tools now.' in prepare
    assert '[Output]' not in prepare
    assert '[Output]' in hooks._user(state, facts='A validated chart')


@pytest.mark.asyncio
async def test_block_inserts_validated_chart_without_model_recopying(monkeypatch):
    from app.harness import modes
    from app.harness.hooks.block import BlockHooks
    from app.harness.state import State
    from app.harness.tools import ToolContext
    from app.util import llm
    chart = 'pie title Fictional Maple\n  "Independent checkout" : 26\n  "Needed assistance" : 4'
    state = State(mode=modes.EDA, ctx=ToolContext(user='fictional'), charts=[chart])
    state.facts = [f'Validated output:\n```mermaid\n{chart}\n```']
    async def stream(messages, **kwargs):
        assert '{{NOTE_CHART_1}}' in messages[1]['content']
        assert chart not in messages[1]['content']
        yield '{{NOTE_'
        yield 'CHART_1}}\n\nA small fictional sample.'
    monkeypatch.setattr(llm, 'stream', stream)
    pieces = [piece async for piece in BlockHooks(title='Fictional Maple').produce(state)]
    assert pieces == [f'```mermaid\n{chart}\n```\n\nA small fictional sample.']
    assert state.content == pieces[0]


@pytest.mark.parametrize('values, expected', [([26, 4], '0 --> 26'), ([-4, -26], '-26 --> 0'), ([-4, 26], '-4 --> 26')])
def test_bar_charts_include_zero_baseline(values, expected):
    from app.harness.tools.blocks import mermaid_xy
    assert f'y-axis "Readers" {expected}' in mermaid_xy('Maple', ['A', 'B'], values, series='Readers')


def test_memoket_rejects_batch_shell_launchers(monkeypatch):
    monkeypatch.setattr(memoket.shutil, 'which', lambda name: 'memoket.cmd')
    with pytest.raises(memoket.ConnectorError, match='Batch launchers'):
        memoket.executable()
