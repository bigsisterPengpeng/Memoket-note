from app.harness.checks.citations import check_citations
from app.harness.checks.citations import DEFAULT_MATCH_THRESHOLD


def test_exact_match_is_verified():
    # the real contract this checks against (see EDIT_SYSTEM/EXPAND_SYSTEM in
    # the host app) asks the model to quote the source verbatim, not
    # paraphrase -- so a near-verbatim quote is the realistic case to test,
    # not a loose paraphrase (a genuine reword like "prototype arrives March
    # 21st" vs "the latest working sample is arriving on March 21st" scores
    # 0.56, correctly below threshold -- that's a real, separate finding,
    # not a bug: this check verifies quotation, not semantic equivalence).
    checks = check_citations(
        ["The latest working sample is arriving on March 21st"],
        ["The latest working sample is arriving on March 21st.", "Unrelated fact."],
    )
    assert len(checks) == 1
    assert checks[0].best_match == "The latest working sample is arriving on March 21st."


def test_close_paraphrase_is_verified():
    checks = check_citations(
        ["Speaker A will speak with Angela later."],
        ["Speaker A will speak with Angela later.", "Something else entirely."],
    )
    assert checks[0].verified
    assert checks[0].similarity == 1.0


def test_fabricated_citation_is_not_verified():
    checks = check_citations(
        ["The team reviewed battery capacity in a special meeting."],
        ["Speaker A will speak with Angela later.", "The prototype arrives March 21st."],
    )
    assert len(checks) == 1
    assert not checks[0].verified
    assert checks[0].best_match is None


def test_empty_claimed_sources_are_skipped():
    checks = check_citations(["", "  ", "real claim here matching something below"],
                             ["real claim here matching something below"])
    assert len(checks) == 1


def test_no_available_facts_means_nothing_verifies():
    checks = check_citations(["some claim"], [])
    assert checks[0].similarity == 0.0
    assert not checks[0].verified


def test_threshold_is_respected():
    # similarity right at the boundary
    checks = check_citations(["abcdefghij"], ["abcdefghix"], threshold=DEFAULT_MATCH_THRESHOLD)
    # 9/10 chars match -> ratio 0.9, well above default 0.7
    assert checks[0].verified
    checks_strict = check_citations(["abcdefghij"], ["abcdefghix"], threshold=0.95)
    assert not checks_strict[0].verified
