"""Manual KITE facts must participate in the same citation graph as extracted facts."""
from app.database import store

FACT = 'note-abcdef123456-manualF1'


def test_manual_fact_ids_are_recognized_and_deduplicated():
    assert store.cited_fact_ids(f'First [{FACT}]. Again [{FACT}].') == [FACT]
    assert store.cited_fact_ids('[ordinary label] [note-abcdef123456-manualF0]') == []


def test_saving_a_manual_citation_creates_a_note_backlink():
    note = store.create_note('demo', 'Reading room', f'The library opens on Tuesday. [{FACT}]')
    assert [n['id'] for n in store.notes_citing('demo', FACT)] == [note['id']]
    assert store.notes_citing('other-user', FACT) == []


def test_reindex_recovers_manual_citations_in_existing_notes():
    note = store.create_note('demo', 'Reading room', f'The library opens on Tuesday. [{FACT}]')
    with store.connect() as connection:
        connection.execute('DELETE FROM note_citations WHERE note_id=?', (note['id'],))
        connection.commit()
    assert store.reindex_citations() == 1
    assert [n['id'] for n in store.notes_citing('demo', FACT)] == [note['id']]


def test_imported_source_formats_match_checks_prompts_and_backlinks():
    import json
    from pathlib import Path
    from app.harness.checks.citations import cited_ids, supplied_ids
    from app.harness.prompts.fragments import facts_block

    cases = json.loads((Path(__file__).resolve().parents[2] / 'shared/citation-ids.json').read_text())
    text = ' '.join(f'Saved evidence [{fid}].' for fid in cases['valid'])
    assert store.cited_fact_ids(text) == cases['valid']
    assert cited_ids(text) == cases['valid']
    assert supplied_ids([f'[{fid}] Original evidence' for fid in cases['valid']]) == set(cases['valid'])
    for fid in cases['valid']:
        assert 'Citation rules:' in facts_block([f'[{fid}] Original evidence'])
    assert store.cited_fact_ids(' '.join(f'[{fid}]' for fid in cases['invalid'])) == []
    note = store.create_note('synthetic-user', 'Imported source citations', text)
    for fid in cases['valid']:
        assert [n['id'] for n in store.notes_citing('synthetic-user', fid)] == [note['id']]
