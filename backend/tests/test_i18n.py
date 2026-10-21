"""Human-facing text follows X-Lang (app/util/i18n.py). Prompts do not."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402
from app.util import i18n  # noqa: E402
from app.util.i18n_zh import ZH  # noqa: E402

HAN = re.compile('[\u3400-\u9fff]')


def test_dictionary_keys_are_english_and_placeholders_match():
    ph = lambda s: sorted(re.findall(r"\{(\w+)\}", s))  # noqa: E731
    for en, zh in ZH.items():
        assert not HAN.search(en), en
        assert ph(en) == ph(zh), (en, zh)


def test_msg_follows_language_and_falls_back_to_english():
    assert i18n.msg("Note not found") == "Note not found"
    tok = i18n.ctx_lang.set("zh")
    try:
        assert i18n.msg("Note not found") == '\u7b14\u8bb0\u4e0d\u5728'
        assert i18n.msg("Never translated sentence") == "Never translated sentence"
    finally:
        i18n.ctx_lang.reset(tok)


def test_pick():
    assert i18n.pick("zh") == "zh" and i18n.pick("zh-CN") == "zh"
    assert i18n.pick("en") == "en" and i18n.pick(None) == "en" and i18n.pick("fr") == "en"


def test_request_header_selects_error_language():
    c = TestClient(app)
    en = c.get("/api/notes", headers={"X-User-Id": "bad id!"})
    zh = c.get("/api/notes", headers={"X-User-Id": "bad id!", "X-Lang": "zh"})
    assert en.status_code == zh.status_code == 400
    assert not HAN.search(en.json()["detail"]), en.json()
    assert HAN.search(zh.json()["detail"])
