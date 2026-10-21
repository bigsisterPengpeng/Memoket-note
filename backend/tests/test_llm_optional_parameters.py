"""A non-reasoning model must work through every completion path."""
import asyncio
import json

import httpx
import pytest

from app.util import llm


@pytest.mark.parametrize('mode', ['complete', 'raw', 'stream', 'events'])
@pytest.mark.parametrize('with_param', [False, True])
def test_retries_rejected_reasoning_parameter_without_losing_output_limit(monkeypatch, mode, with_param):
    sent = []

    def respond(request):
        body = json.loads(request.content)
        sent.append(body)
        if 'reasoning_effort' in body:
            return httpx.Response(400, json={'error': {
                'message': 'Unrecognized request argument supplied: reasoning_effort',
                'param': 'reasoning_effort' if with_param else None,
                'type': 'invalid_request_error',
            }})
        if body['stream']:
            chunk = {'choices': [{'delta': {'content': 'A sourced draft.'}, 'finish_reason': 'stop'}]}
            return httpx.Response(200, text=f'data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n',
                                  headers={'Content-Type': 'text/event-stream'})
        return httpx.Response(200, json={'choices': [{'message': {'content': 'A sourced draft.'}}]})

    client = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, 'AsyncClient', lambda **kw: client(transport=httpx.MockTransport(respond), **kw))
    monkeypatch.setattr(llm.store, 'get_active_llm_config', lambda: {
        'base_url': 'https://model.example/v1', 'api_key': 'test-key',
        'model': 'gpt-4.1', 'family': 'openai',
    })
    monkeypatch.setattr(llm, '_record', lambda *args: None)

    async def run():
        messages = [{'role': 'user', 'content': 'Draft from the saved source.'}]
        if mode == 'complete':
            return await llm.complete(messages, max_tokens=80)
        if mode == 'raw':
            tool = {'type': 'function', 'function': {'name': 'recall', 'parameters': {'type': 'object'}}}
            return (await llm.complete_raw(messages, max_tokens=80, tools=[tool]))['content']
        if mode == 'stream':
            return ''.join([part async for part in llm.stream(messages, max_tokens=80)])
        return ''.join([part async for kind, part in llm.stream_events(messages, max_tokens=80) if kind == 'output'])

    assert asyncio.run(run()) == 'A sourced draft.'
    assert len(sent) == 2
    assert 'reasoning_effort' not in sent[1]
    assert sent[1]['max_completion_tokens'] == sent[0]['max_completion_tokens'] == 80 + llm.REASONING_RESERVE
    assert sent[1]['messages'] == sent[0]['messages']
    if mode == 'raw':
        assert sent[1]['tools'] == sent[0]['tools']


@pytest.mark.parametrize('status,message,param', [
    (401, 'Unrecognized request argument supplied: reasoning_effort', None),
    (429, 'Unrecognized request argument supplied: reasoning_effort', None),
    (400, 'Invalid messages. See reasoning_effort documentation.', 'messages'),
    (400, 'Unrecognized request argument supplied: unknown_field', None),
])
def test_does_not_hide_authentication_quota_or_unrelated_errors(status, message, param):
    payload = {'reasoning_effort': 'low', 'max_completion_tokens': 100}
    assert not llm._drop_rejected_param(payload, status, json.dumps({'error': {'message': message, 'param': param}}).encode())
    assert payload['reasoning_effort'] == 'low'
