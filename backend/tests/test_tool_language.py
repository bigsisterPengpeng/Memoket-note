"""English tool text must retain evidence boundaries and recoverable failures."""

from app.harness import query_cache, tools
from app.harness.agent_loop import ToolTrace
from app.harness.tools import memory_tools, registry


def test_english_memory_metadata_stays_attached_to_its_fact():
    formatted = memory_tools._fmt_facts([
        {"id": "fact-1", "text": "Launch is scheduled for April.",
         "date": "2026-04-02", "who": "Alex", "entities": ["Project A"]}
    ])
    trace = ToolTrace(calls=[("filter_facts", {}, "1 facts total; returning 1:\n" + formatted)])
    facts = trace.as_facts()
    assert len(facts) == 1
    assert "Launch is scheduled for April." in facts[0]
    assert "2026-04-02" in facts[0] and "Subjects: Project A" in facts[0]
    assert "facts total" not in facts[0]


def test_english_empty_result_is_not_treated_as_evidence():
    trace = ToolTrace(calls=[("search_memory", {}, memory_tools.EMPTY_KB),
                             ("filter_facts", {}, "(No matching facts)")])
    assert trace.as_facts() == []


def test_transient_error_from_long_tool_name_is_not_cached(monkeypatch):
    calls = []

    def fail(ctx, question):
        calls.append(question)
        raise registry.ToolError("Try again later")

    tool = registry.Tool("search_session_context", "Test lookup", {}, ["question"], fail)
    monkeypatch.setitem(registry._REGISTRY, tool.name, tool)
    ctx = tools.ToolContext(user="test-user")
    for _ in range(2):
        result = query_cache.dispatch(tool.name, {"question": "Which session?"}, ctx)
        assert result.startswith("Execution failed")
    assert calls == ["Which session?", "Which session?"]


def test_all_builtin_tool_instructions_and_parameter_descriptions_are_english():
    import re

    han = re.compile(r"[\u3400-\u9fff]")
    for name in tools.names():
        tool = registry.get(name)
        assert tool is not None
        assert not han.search(tool.description), name
        for param in tool.params.values():
            assert not han.search(param.get("description", "")), name


def test_english_occasion_scopes_trigger_session_retrieval():
    from app.harness.agent_loop import is_scoped_question

    for question in (
        "What else did we decide in that meeting?",
        "Recall the previous conversation about launch dates.",
        "During the planning meeting, who owned the next step?",
    ):
        assert is_scoped_question(question)
    assert not is_scoped_question("What is the launch date?")


def test_english_table_summary_preserves_numeric_results():
    import json
    from app.harness.tools import data_tools

    ctx = tools.ToolContext(user="test", content=(
        "| Name | Score |\n|---|---|\n| A | 10 |\n| B | 20 |\n| C | 30 |\n"
    ))
    columns = json.loads(data_tools.describe_table(ctx))
    score = next(column for column in columns if column["column"] == "Score")
    assert score["type"] == "numeric" and score["valid"] == 3
    assert score["mean"] == 20 and score["median"] == 20 and score["sum"] == 60
    assert score["missing"] == 0
    assert set(score) >= {"min", "max", "P25", "P75", "stddev"}


def test_generated_chart_defaults_and_empty_notices_are_english():
    import re
    from app.harness.tools import data_tools

    ctx = tools.ToolContext(user="test")
    chart = data_tools.render_chart(ctx, kind="bar", title="Counts", labels=["A", "B"], values=[10, 20])
    assert 'y-axis "Value"' in chart
    assert not re.search(r"[\u3400-\u9fff]", chart)
    for result in (data_tools.list_tables(ctx), data_tools.numbers_near_cursor(ctx)):
        assert not re.search(r"[\u3400-\u9fff]", result)
        assert registry.is_tool_notice(result)


def test_current_memory_tool_output_populates_ledger_dates_totals_and_topics(monkeypatch):
    from app.harness.middleware import ledger
    from app.harness.checks import relevance

    rows = [{"id": "fixture-1-A", "text": "Aurora review completed.", "date": "2026-04-02"}]
    formatted = memory_tools._fmt_facts(rows)
    result = "1200 facts total; returning 1:\n" + formatted
    led = ledger.blank()
    ledger.fold(led, [("filter_facts", {"topic": "aurora"}, result)])
    assert led["facts"]["fixture-1-A"]["when"] == "2026-04-02"
    assert led["axes"]["topic:aurora"] == {"total": 1200, "taken": 1}
    assert relevance.sampled_ids([("filter_facts", {}, result)]) == {"fixture-1-A"}
    monkeypatch.setattr(memory_tools, "UserMemory", lambda _: type("Memory", (), {
        "topics": lambda self: [{"code": "aurora", "fact_count": 1200, "aliases": []}]
    })())
    topics = memory_tools.list_topics(tools.ToolContext(user="synthetic"))
    assert ledger.note_topics(led, topics) == 1
    assert "aurora: 1200 records available; retrieved 1 records" in ledger.gap_summary(led)
