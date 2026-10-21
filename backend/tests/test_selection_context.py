'Regression tests for selection context.'

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.harness.prompts.selection import (  # noqa: E402
    expand_user, rewrite_user, selection_context, verify_user,
)


def _long() -> str:
    return "\n\n".join(f'\u7b2c{i}\u6bb5\uff1a\u8ba8\u8bba\u4e86\u6392\u671f\u548c\u6837\u673a{i}\uff0c\u786c\u4ef6\u90e8\u5206\u5e94\u628a\u8282\u70b9\u3001\u72b6\u6001\u548c\u8bc1\u636e\u62c6\u5f00\u8bb0\u5f55\u3002' for i in range(600))


def test_short_content_untouched():
    assert selection_context('\u77ed\u6b63\u6587', '\u77ed') == '\u77ed\u6b63\u6587'


def test_long_content_windowed_around_selection():
    content = _long()
    sel = '\u8ba8\u8bba\u4e86\u6392\u671f\u548c\u6837\u673a300'
    ctx = selection_context(content, sel)
    assert sel in ctx
    assert len(ctx) < 8000
    assert ctx.startswith("… (") and "preceding characters omitted)" in ctx and ctx.rstrip().endswith("trailing characters omitted)")

    body = ctx.split("\n\n", 1)[1]
    assert body.startswith('\u7b2c')


def test_selection_not_found_falls_back_to_head():
    ctx = selection_context(_long(), '\u4e0d\u5b58\u5728\u7684\u53e5\u5b50')
    assert ctx.startswith('\u7b2c0\u6bb5') and 'trailing characters omitted' in ctx


def test_three_prompts_all_use_window():
    content = _long()
    sel = '\u8ba8\u8bba\u4e86\u6392\u671f\u548c\u6837\u673a300'
    for text in (rewrite_user(content, sel, "", []), expand_user(content, sel), verify_user(content, sel, [])):
        assert sel in text and 'preceding characters omitted' in text and len(text) < 12000
