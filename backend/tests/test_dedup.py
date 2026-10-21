from app.harness.middleware.repeats import find_repeats


def test_finds_near_identical_paragraphs():
    a = "The migration was necessary because the old system could not scale past 10k users."
    b = "The migration was necessary because the old system couldn't scale beyond 10k users."
    content = f"{a}\n\nSome unrelated paragraph about something else entirely here.\n\n{b}"
    hints = find_repeats(content, threshold=0.6)
    assert len(hints) == 1
    assert {hints[0].a, hints[0].b} == {a, b}


def test_no_hints_for_distinct_paragraphs():
    content = (
        "The migration was necessary because the old system could not scale.\n\n"
        "The new system uses a completely different architecture based on message queues.\n\n"
        "Rollout is planned for next quarter across all regions gradually."
    )
    assert find_repeats(content) == []


def test_short_paragraphs_ignored():
    # short lines (e.g. lone headings) shouldn't trigger even if identical
    content = "Intro\n\nIntro"
    assert find_repeats(content) == []


def test_max_hints_caps_and_dedupes_paragraph_reuse():
    para = "This exact sentence about the migration timeline gets repeated many times over."
    content = "\n\n".join([para] * 6)
    hints = find_repeats(content, threshold=0.5, max_hints=2)
    assert len(hints) <= 2
    seen = set()
    for hint in hints:
        assert hint.a not in seen and hint.b not in seen
        seen.add(hint.a)
        seen.add(hint.b)


def test_hints_sorted_by_similarity_descending():
    content = "\n\n".join(
        [
            "Paragraph one talks about apples and oranges in a long descriptive sentence.",
            "Paragraph one talks about apples and oranges in a long descriptive sentence!",
            "This paragraph is about something totally different, like rocket engines flying.",
            "This paragraph discusses something totally different, like rocket engines soaring.",
        ]
    )
    hints = find_repeats(content, threshold=0.5, max_hints=5)
    similarities = [h.similarity for h in hints]
    assert similarities == sorted(similarities, reverse=True)
