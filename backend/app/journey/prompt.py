"""English instructions for daily and period activity reviews.

Durations are computed by code. Model output is checked separately and legacy
report headings remain readable by the report checker.
"""

from __future__ import annotations

def prompt_tr(en: str, **params) -> str:
    """Format model instructions independently of the UI locale."""
    return en.format(**params) if params else en


_tr = prompt_tr


REPORT_SYSTEM_EN = """You are a screen-activity review assistant. What you are given is the
screen-activity log of one day in chronological order - each entry is a one-sentence description
of what was on the screen at that moment. Write a review of that day.

Use the following structure (all markdown level-2 headings; leave out a section entirely if it
has no content, do not pad):
## What moved forward
## Where it got stuck
## Unplanned

Requirements:
- **Do not write a "where the time went" section and do not compute any durations** - the
  program has already computed durations, and if you recompute them you will get them wrong. When
  you need to mention how long something took, use relative wording such as "morning" or
  "afternoon" based on the timestamps given, and do not state specific minute counts.
- 2-4 items per section, one sentence per item, as a "- " list.
- **Every item must carry something concrete**: a file name, function name, document title,
  person's name, error, number. Not a single item like "continued development work".
- "Where it got stuck" only holds what has grounds: going back to the same place again and
  again, the same error appearing repeatedly, something worked on for a long time with no sign of
  moving on. **If there is no such sign, leave the whole section out**; do not describe normal
  back-and-forth switching as being stuck.
- **One item per matter.** Saying the same thing again from another angle means the section says
  one thing but takes up two lines.
- "Unplanned" holds things that do not look like part of the day's main line but really took
  time. Leave it out if you cannot tell.
- Rely only on the records given; do not invent anything that was not mentioned.
- Output the markdown body directly, with no extra explanation or prefix/suffix.
"""

REPORT_SYSTEM = _tr(REPORT_SYSTEM_EN)


def report_user(date: str, lines: list[str], churn: str = "") -> str:
    """The records go in as they are, in time order. **Include the time of day**: "where it got
    stuck" can only be seen from the distribution over time (touching it once in the morning and
    twice more in the afternoon is not the same as touching it three times in a row)."""
    body = "\n".join(lines) if lines else _tr("(no records for this day)")
    extra = f"\n\n{churn}" if churn else ""
    return _tr("Here is the screen-activity log for {date}:\n\n{body}{extra}\n\nWrite the review of this day as instructed.",
               date=date, body=body, extra=extra)


# ---------------------------------------------------------------- cross-time report (section 4.2)

SPAN_SYSTEM_EN = """You are a review assistant. What you are given is **the daily report of every day
in a period** (not the raw records); write a review of the period.

Use the following structure (markdown level-2 headings; leave out a section entirely if it has no content):
## What the period was mainly about
## How far things got
## Places that kept getting stuck
## Changes worth noting

Requirements:
- **Write threads, not a running log.** "On the 9th did A, on the 10th did B, on the 11th did C"
  just copies the daily reports - what is really valuable is "A dragged from the 9th to the 13th
  and was interrupted by B twice along the way".
- In the first section group the period into 2-4 threads, **one sentence per thread**, saying clearly what the matter is.
- In the second section write about the same threads, one by one, saying clearly how far each got
  and where it stands now. **No more than two sentences each.**
- **Do not stitch numbers that appeared on different days into a trend.** 1020 on the 10th and
  1014 on the 11th are just two numbers; if the daily reports do not say it is changing, do not
  write "dropped from 1020 to 1014" - that is a made-up causation.
- "Places that kept getting stuck" holds only what **repeats across days**: back-and-forth within
  one day is the daily report's business, and it is the same problem coming back after three days
  that belongs in this section. Leave the whole section out if there is none.
- "Changes worth noting" is about a shift of center of gravity: mainly on X in the first half, turned to Y in the second.
- Every item must carry something concrete: file name, feature name, person's name, number. Not
  a single item without a specific name.
- **Do not compute durations yourself.** Durations already written in the daily reports may be
  quoted, but do not add them, subtract them, or derive a new number from them - those numbers
  are computed by the program, and what you compute is not.
- Rely only on the daily reports given; do not invent. Output the markdown body directly, with no extra explanation or prefix/suffix.
"""

SPAN_SYSTEM = _tr(SPAN_SYSTEM_EN)


def span_user(date_from: str, date_to: str, reports: list[tuple[str, str]]) -> str:
    """The daily reports go in day by day as they are. **What is fed is the daily reports, not
    the raw records**: 30 days of segments is hundreds of thousands of tokens, and only buys an
    averaged-out piece of nonsense (section 4.2)."""
    body = "\n\n".join(f"### {d}\n\n{md.strip()}" for d, md in reports)
    return _tr("Here are the daily reports for every day from {date_from} to {date_to}:\n\n{body}\n\nWrite the review of this period as instructed.",
               date_from=date_from, date_to=date_to, body=body)
