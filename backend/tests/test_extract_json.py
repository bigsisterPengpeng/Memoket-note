'Regression tests for extract json.'

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.util.llm import extract_json  # noqa: E402


def test_plain_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_plain_array():
    assert extract_json('[1, 2, 3]') == [1, 2, 3]


def test_object_wrapped_in_prose():
    assert extract_json('\u8fd9\u662f\u7ed3\u679c\uff1a{"a": 1} \u5e0c\u671b\u6709\u5e2e\u52a9') == {"a": 1}


def test_fenced_code_block():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_array_not_mistaken_for_first_element():

    assert extract_json('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]


def test_genuinely_truncated_object_gets_repaired():


    truncated = '{"text":"\u8fd9\u9879\u5de5\u4f5c\u5f88\u91cd\u8981\uff0c\u8bf7\u5927\u5bb6\u4e88\u4ee5\u91cd\u89c6\u3002","reason":"\u6539\u5f97\u66f4\u7b80\u6d01"'
    assert extract_json(truncated) == {
        "text": '\u8fd9\u9879\u5de5\u4f5c\u5f88\u91cd\u8981\uff0c\u8bf7\u5927\u5bb6\u4e88\u4ee5\u91cd\u89c6\u3002',
        "reason": '\u6539\u5f97\u66f4\u7b80\u6d01',
    }


def test_truncated_array_gets_repaired():
    truncated = '[{"op":"replace","anchor":"foo","text":"bar"'
    assert extract_json(truncated) == [{"op": "replace", "anchor": "foo", "text": "bar"}]


def test_truncated_mid_string_gets_repaired():

    truncated = '{"text":"\u6ca1\u5199\u5b8c\u7684\u53e5\u5b50'
    assert extract_json(truncated) == {"text": '\u6ca1\u5199\u5b8c\u7684\u53e5\u5b50'}


def test_truncated_nested_object_gets_repaired():
    truncated = '{"outer":{"inner":"value"'
    assert extract_json(truncated) == {"outer": {"inner": "value"}}


def test_genuinely_invalid_json_still_returns_none():


    assert extract_json("{'a': 1}") is None


def test_empty_string_returns_none():
    assert extract_json("") is None


def test_no_json_present_returns_none():
    assert extract_json('\u8fd9\u91cc\u6ca1\u6709\u4efb\u4f55 JSON\uff0c\u53ea\u662f\u4e00\u53e5\u8bdd\u3002') is None
