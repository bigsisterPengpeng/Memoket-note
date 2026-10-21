"""The **counted half** of the daily report (docs/daily-journey-plan.md section 4.1).

An old rule of this repo: whatever rules can compute exactly is not handed to the model. Durations,
blocks of continuous focus, places returned to again and again are all computed here - a model counting
durations gets them wrong, and when it does it reads exactly like getting them right.
"""

from __future__ import annotations

from app.journey.stats import CHURN_VISITS, day_stats, render_churn, render_time_block, say_span


def seg(start: str, end: str, app: str = "Code", title: str = "", desc: str = "x"):
    return {"start": f"2026-09-14T{start}:00+08:00", "end": f"2026-09-14T{end}:00+08:00",
            "app": app, "title": title, "desc": desc}


def test_a_day_without_records_still_computes():
    st = day_stats("2026-09-14", [])
    assert st.total_secs == 0 and st.apps == [] and st.first is None
    assert "No records for this day" in render_time_block(st)


def test_aggregated_by_app_and_sorted_by_duration():
    st = day_stats("2026-09-14", [
        seg("09:00", "09:30", "Code"),
        seg("09:30", "09:40", "Safari"),
        seg("10:00", "11:00", "Code"),
    ])
    assert [(a.app, a.segments) for a in st.apps] == [("Code", 2), ("Safari", 1)]
    assert st.apps[0].secs == 90 * 60
    assert st.total_secs == 100 * 60


def test_gaps_are_not_counted_in_total_but_reported_separately():
    """"Recorded 4 hours" and "from 9 in the morning to 6 in the evening" are two numbers; merging them into one is deceptive."""
    st = day_stats("2026-09-14", [seg("09:00", "10:00"), seg("14:00", "15:00")])
    assert st.total_secs == 2 * 3600            # actually recorded
    assert st.span_secs == 6 * 3600             # first to last
    assert st.gap_secs == 4 * 3600
    block = render_time_block(st)
    assert "recorded 2 h, with 4 h not recorded in between." in block


def test_consecutive_segments_of_one_app_merge_into_one_focus_stretch():
    st = day_stats("2026-09-14", [
        seg("09:00", "09:20", "Code"), seg("09:20", "09:50", "Code"),
        seg("09:50", "10:05", "Safari"),
    ])
    assert [(x.app, x.secs) for x in st.stretches] == [("Code", 50 * 60), ("Safari", 15 * 60)]


def test_a_focus_stretch_names_the_file_it_was_on():
    """"52 minutes in Code this afternoon" says almost nothing; "in capture.ts" does.
    It takes the title that took the most time in the block, not the first one."""
    st = day_stats("2026-09-14", [
        seg("09:00", "09:05", "Code", "a.py"),
        seg("09:05", "09:40", "Code", "capture.ts"),
        seg("09:40", "09:45", "Code", "a.py"),
    ])
    assert st.stretches[0].title == "capture.ts"
    assert "Code · capture.ts" in render_time_block(st)


def test_too_long_a_gap_breaks_the_focus_stretch():
    """Two stretches of Code separated by lunch are not "two hours of continuous focus"."""
    st = day_stats("2026-09-14", [seg("09:00", "10:00", "Code"), seg("12:00", "13:00", "Code")])
    assert [x.secs for x in st.stretches] == [3600, 3600]


def test_too_short_blocks_are_not_focus_stretches():
    st = day_stats("2026-09-14", [seg("09:00", "09:05", "Code"), seg("09:05", "09:09", "Safari")])
    assert st.stretches == []


def test_churn_needs_returning_to_one_place_consecutive_segments_count_once():
    a = ("Code", "journey.py")
    st = day_stats("2026-09-14", [
        seg("09:00", "09:10", *a), seg("09:10", "09:20", *a),   # consecutive = one stay
        seg("09:20", "09:25", "Safari", '\u6587\u6863'),
        seg("09:25", "09:35", *a),                              # second time
        seg("09:35", "09:40", "Safari", '\u6587\u6863'),
        seg("09:40", "09:50", *a),                              # third time
    ])
    churn = {c.title: c for c in st.churn}
    assert churn["journey.py"].visits == CHURN_VISITS
    assert churn["journey.py"].secs == 40 * 60
    assert '\u6587\u6863' not in churn                                   # only visited twice, does not count
    assert "journey.py" in render_churn(st)


def test_segments_without_title_do_not_count_for_churn():
    """Without a title we cannot tell whether it is the same place - `Code` and `Code` may be two completely different files."""
    st = day_stats("2026-09-14", [
        seg("09:00", "09:10", "Code", ""), seg("09:10", "09:15", "Safari", ""),
        seg("09:15", "09:25", "Code", ""), seg("09:25", "09:30", "Safari", ""),
        seg("09:30", "09:40", "Code", ""),
    ])
    assert st.churn == []


def test_shuffled_on_disk_order_still_computes_right():
    """Filling in descriptions or moving across day directories can shuffle the order, and both continuous focus and churn depend on order."""
    rows = [seg("14:00", "15:00", "Safari"), seg("09:00", "10:00", "Code")]
    st = day_stats("2026-09-14", rows)
    assert st.first.hour == 9 and st.last.hour == 15
    assert st.gap_secs == 4 * 3600


def test_a_bad_timestamp_row_is_skipped_rest_still_computes():
    st = day_stats("2026-09-14", [seg("09:00", "10:00"), {"app": "X", "start": '\u574f', "end": '\u66f4\u574f'}])
    assert st.total_secs == 3600 and [a.app for a in st.apps] == ["Code"]


def test_durations_in_plain_words():
    assert say_span(20) == "under 1 min"
    assert say_span(600) == "10 min"
    assert say_span(3600) == "1 h"
    assert say_span(3600 + 720) == "1 h 12 min"


def test_the_time_section_is_written_by_code_not_the_model():
    """This section goes into the daily report verbatim and the prompt says not to recompute it - so it must be complete on its own."""
    st = day_stats("2026-09-14", [seg("09:00", "10:00", "Code", "a.py"),
                                  seg("10:00", "10:30", "Safari", '\u6587\u6863')])
    block = render_time_block(st)
    assert block.startswith("## Where the time went")
    assert "**Code** 1 h" in block and "**Safari** 30 min" in block
    assert "09:00 – 10:30" in block


def test_time_section_follows_the_request_language_and_churn_follows_the_prompt():
    """The time block lands in the user's note, so it speaks the UI language; the churn hints are
    part of the model prompt, so they remain English independently of the UI locale."""
    from app.util import i18n

    st = day_stats("2026-09-14", [seg("09:00", "10:00", "Code", "a.py")])
    tok = i18n.ctx_lang.set("zh")
    try:
        assert render_time_block(st).startswith('## \u65f6\u95f4\u53bb\u54ea\u4e86')   # "where the time went"
        assert say_span(3600 + 720) == '1 \u5c0f\u65f6 12 \u5206\u949f'
    finally:
        i18n.ctx_lang.reset(tok)
    churny = day_stats("2026-09-14", [
        seg("09:00", "09:10", "Code", "a.py"), seg("09:10", "09:20", "Safari", "doc"),
        seg("09:20", "09:30", "Code", "a.py"), seg("09:30", "09:40", "Safari", "doc"),
        seg("09:40", "09:50", "Code", "a.py"), seg("09:50", "10:00", "Safari", "doc"),
        seg("10:00", "10:10", "Code", "a.py")])
    hint = render_churn(churny)
    assert hint and "times" in hint  # Model instructions stay English regardless of UI locale.
