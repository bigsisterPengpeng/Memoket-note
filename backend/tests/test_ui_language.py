"""Generated navigation labels follow the request locale, not source-data language."""

import re
from types import SimpleNamespace

from memoket_kite.core.algebra import Store
from memoket_kite.core.vocab import Vocab

from app.database.kb import virtual_tree
from app.util import i18n


def test_default_knowledge_tree_labels_are_english_with_optional_locale_translation():
    mem = SimpleNamespace(_index=lambda: (Store(), Vocab()))
    token = i18n.ctx_lang.set("en")
    try:
        labels = {row["note_id"]: row["title"] for row in virtual_tree.build(mem)}
        assert labels["kb"] == "Knowledge base"
        assert labels["kb:topics"] == "Topics"
        assert labels["kb:graph"] == "Topic map"
        assert not re.search(r"[\u3400-\u9fff]", "".join(labels.values()))
        i18n.ctx_lang.set("zh")
        localized = {row["note_id"]: row["title"] for row in virtual_tree.build(mem)}
        assert localized["kb"] == '\u77e5\u8bc6\u5e93'
        assert localized.keys() == labels.keys()
    finally:
        i18n.ctx_lang.reset(token)


def test_new_journals_are_english_and_repeated_requests_reuse_the_note(tmp_path, monkeypatch):
    from datetime import date
    from app.database import store

    monkeypatch.setattr(store, "_db_path", lambda: tmp_path / "notes.sqlite3")
    day = date(2026, 10, 20)
    first = store.today_note("synthetic", day)
    second = store.today_note("synthetic", day)
    assert first["id"] == second["id"]
    assert first["title"] == "10-20 Tuesday"
    assert first["content"] == "# 2026-10-20 Tuesday\n\n"
    assert not re.search(r"[\u3400-\u9fff]", first["title"] + first["content"])


def test_existing_legacy_journal_paths_are_reused_without_renaming(tmp_path, monkeypatch):
    from datetime import date
    from app.database import store

    monkeypatch.setattr(store, "_db_path", lambda: tmp_path / "notes.sqlite3")
    parent = store.ROOT_ID
    for title in ('\u65e5\u8bb0', "2026", '10 \u6708', '10-20 \u5468\u4e8c'):
        note = store.create_note("synthetic", title, "", parent)
        parent = note["id"]
    store.update_note("synthetic", parent, title=title, content="Existing user text.")
    loaded = store.today_note("synthetic", date(2026, 10, 20))
    assert loaded["id"] == parent
    assert loaded["content"] == "Existing user text."
    assert loaded["title"] == '10-20 \u5468\u4e8c'
