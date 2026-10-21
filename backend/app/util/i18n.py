"""Language of human-facing text (errors, job details, stop reasons). Prompts do not go through here.

English source text is the key: `msg("Note not found")` returns it as-is in English mode and
looks it up in `i18n_zh.ZH` in Chinese mode, falling back to English when missing.
The language comes from the `X-Lang` request header (set into a contextvar by the middleware in
main.py). Background jobs have no request: the caller reads `current()` before `bg.add_task`
and passes it along.
"""

from __future__ import annotations

import contextvars

from .i18n_zh import ZH

ctx_lang: contextvars.ContextVar[str] = contextvars.ContextVar("lang", default="en")


def pick(header: str | None) -> str:
    """Request header -> 'en' / 'zh'. Anything unknown is English (same as no header)."""
    v = (header or "").strip().lower()
    return "zh" if v.startswith("zh") else "en"


def current() -> str:
    return ctx_lang.get()


def msg(en: str, **params) -> str:
    """Translate one human-facing sentence. `{name}` placeholders match on both sides; interpolation
    happens here in both languages, so callers must not f-string first."""
    s = ZH.get(en, en) if ctx_lang.get() == "zh" else en
    if params:
        try:
            s = s.format(**params)
        except (KeyError, IndexError, ValueError):
            pass
    return s


def has_zh(en: str) -> bool:
    return en in ZH
