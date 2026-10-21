"""Stock Whisper hallucinations from silent audio must not reach the knowledge base.

Round 632 measured 16 of 20,406 facts: a video-channel donation outro (9),
a goodbye outro (4), and a stock Mandarin sentence (3). No speaker said them;
Whisper recited training-data endings where there was no speech. Even a few
such facts matter because retrieval can cite them in the user's writing.

The filter lives at asr.transcribe(), the common entry for knowledge-base imports
and editor voice input. CJK fixtures below retain their exact runtime wording.
"""

from __future__ import annotations

from app.database.ingest.asr import drop_hallucinations as drop


def test_removes_whole_hallucinations_preserving_surrounding_text():
    assert drop('\u4eca\u5929\u5b9a\u4e86\u7535\u6c60\u65b9\u6848\u3002\u8bf7\u4e0d\u541d\u70b9\u8d5e\u8ba2\u9605\u8f6c\u53d1\u6253\u8d4f\u652f\u6301\u660e\u955c\u4e0e\u70b9\u70b9\u680f\u76ee\u3002\u660e\u5929\u7ee7\u7eed\u3002') \
        == '\u4eca\u5929\u5b9a\u4e86\u7535\u6c60\u65b9\u6848\u3002\u660e\u5929\u7ee7\u7eed\u3002'
    assert drop('\u8fd9\u53e5\u5b50\u662f\u666e\u901a\u8bdd\u7684\u53e5\u5b50\u3002\u6211\u4eec\u7ee7\u7eed\u8bf4\u6837\u673a\u3002') == '\u6211\u4eec\u7ee7\u7eed\u8bf4\u6837\u673a\u3002'
    assert drop('\u8c22\u8c22\u89c2\u770b\uff0c\u4e0b\u6b21\u89c1\uff01') == ""


def test_preserves_user_discussion_of_subscription_business():
    """Broad subscribe/thanks/subtitle patterns matched 133 real sentences about the
    user's email subscription funnel. Match whole sentences to avoid deleting them."""
    for keep in [
        '\u8fd9\u91cc\u53c8\u662f\u4e00\u4e2a\u8ba2\u9605\u6846',
        '\u771f\u5b9e\u7684\u8ba2\u9605\u7684\u4f8b\u5b50\u662f\u6a21\u62df\u4e00\u4e2a\u7528\u6237\u4ece facebook \u7684\u5b98\u65b9\u8d26\u53f7\u53d1\u4e00\u4e2a\u5e26\u8ddf\u8e2a\u94fe\u63a5\u7684\u5e16\u5b50\u3002',
        '\u8ba2\u9605\u6d41\u7a0b\u4e00\u76f4\u8d70\u901a\uff0c\u53ea\u662f\u65e0\u6cd5\u8bc6\u522b\u7528\u6237\u6765\u6e90\u3002',
        '\u4ed6\u8ba2\u9605\u4e4b\u540e\uff0c\u56e0\u4e3a\u8fd9\u91cc\u9762\u8981\u8bbe\u7f6e\u7684\u662f\u90a3\u79cd\u81ea\u52a8\u7684\u3002',
        '\u8c22\u8c22\u89c2\u770b\u4e86\u8fd9\u4e2a demo\uff0c\u6211\u4eec\u518d\u770b\u4e0b\u4e00\u7248\u3002',
    ]:
        assert drop(keep) == keep, keep


def test_accepts_empty_and_hallucination_only_input():
    assert drop("") == ""
    assert drop('\u8c22\u8c22\u89c2\u770b\uff0c\u4e0b\u6b21\u89c1\uff01 \u8c22\u8c22\u89c2\u770b\uff0c\u4e0b\u6b21\u89c1\uff01') == ""
