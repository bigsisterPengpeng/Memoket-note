"""Deterministic checks: what code can decide, code decides.

This is not fastidiousness. The scorer and the thing being scored are the
same local model, so its blind spots line up exactly with the writer's. Real
examples it waved through:

* a block whose "charts" were sentences like ``[bar chart: clicks by
  channel ...]`` -- scored ``has_charts = 2``
* mermaid the model had hand-written by copying a tool's output and adding a
  y-axis range, which makes the chart fail to render -- scored as valid

Every check here is a pure function of ``State``. That makes them unit
testable against real failing output, and means a check can never be the
thing that breaks a run.
"""

from .budget import section_budget
from .charts import chart_readable, chart_restates_list, charts_from_tools, no_fake_charts
from .claims import unsupported_specifics
from .grounding import (citations_exist, citations_present, citations_hold, material_thin,
                        material_used, no_audit_voice, no_placeholder)
from .language import language_consistent, no_foreign_script, no_junk_tail
from .numbers import chart_numbers_grounded, numbers_from_tools
from .pick import pick_dimension
from .shape import output_not_json
from .structure import (heading_fits, no_echoed_text, no_repeated_lists, no_restated_paragraph,
                        no_same_sources_twice, outline_intact, table_columns_match,
                        table_present, tail_clashes)
from .workflow import workflow_quality

__all__ = [
    "pick_dimension",
    "output_not_json",
    "section_budget",
    "chart_numbers_grounded",
    "chart_readable",
    "chart_restates_list",
    "charts_from_tools",
    "language_consistent",
    "no_foreign_script",
    "no_junk_tail",
    "citations_exist",
    "citations_present",
    "no_echoed_text",
    "no_repeated_lists",
    "no_restated_paragraph",
    "no_same_sources_twice",
    "citations_hold",
    "heading_fits",
    "table_columns_match",
    "table_present",
    "material_thin",
    "material_used",
    "no_audit_voice",
    "no_fake_charts",
    "no_placeholder",
    "numbers_from_tools",
    "outline_intact",
    "tail_clashes",
    "unsupported_specifics",
    "workflow_quality",
]
