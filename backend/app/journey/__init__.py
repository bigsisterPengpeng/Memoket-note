"""The half of screen activity (Daily Journey) that can be computed exactly **without a model**.

This package holds pure functions only: given one day's segments, work out durations, blocks of
continuous focus, and places that were returned to again and again.
`routers/journey.py` does the I/O and model calls; nothing here touches either.

Drawing that line is an old rule of this repo: **whatever rules can compute exactly is not handed
to the model**. If the model were asked to count the "where the time went" section of the daily
report, it would count wrong - and when it counts wrong it reads exactly like when it counts right.
"""

from .runs import group_runs, similar
from .stats import AppSpan, Churn, DayStats, Stretch, day_stats, render_time_block

__all__ = ["AppSpan", "Churn", "DayStats", "Stretch", "day_stats", "group_runs",
           "render_time_block", "similar"]
