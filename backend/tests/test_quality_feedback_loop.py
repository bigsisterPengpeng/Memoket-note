from __future__ import annotations

from app.database import store
from app.editor import style_anchors
from app.harness import modes
from app.harness.middleware.revise import actionable_revision
from app.harness.state import State
from app.harness.tools import ToolContext
from app.harness.types import DimensionScore, Evaluation


def test_style_anchors_same_note_first_then_same_workflow():
    user = "u"
    same = '\u8fd9\u662f\u5f53\u524d\u7b14\u8bb0\u91cc\u7684\u4e00\u6bb5\u5b8c\u6574\u6587\u5b57\uff0c\u5b83\u6709\u8db3\u591f\u957f\u5ea6\uff0c\u53ef\u4ee5\u8ba9\u6a21\u578b\u5b66\u4e60\u4f5c\u8005\u81ea\u5df1\u7684\u53e5\u957f\u3001\u8282\u594f\u548c\u8bed\u6c14\u3002'
    note = store.create_note(user, '\u5f53\u524d', same)
    store.set_intent(user, note["id"], {"workflow": "weekly", "goal": '\u5468\u62a5', "source": "user"})
    old = store.create_note(user, '\u65e7\u5468\u62a5', '\u8fd9\u662f\u540c\u4e00\u5de5\u4f5c\u6d41\u91cc\u7684\u53e6\u4e00\u6bb5\u65e7\u6587\u5b57\uff0c\u5b83\u53ea\u5728\u5f53\u524d\u7b14\u8bb0\u6837\u672c\u4e0d\u8db3\u65f6\u8865\u8fdb\u6765\uff0c\u4e0d\u80fd\u62a2\u5728\u5f53\u524d\u6587\u5b57\u524d\u9762\u3002')
    store.set_intent(user, old["id"], {"workflow": "weekly", "goal": '\u5468\u62a5', "source": "user"})
    other = store.create_note(user, '\u65e5\u8bb0', '\u8fd9\u662f\u522b\u7684\u4f53\u88c1\u91cc\u7684\u6587\u5b57\uff0c\u5373\u4f7f\u5199\u5f97\u5f88\u957f\uff0c\u4e5f\u4e0d\u5e94\u8be5\u8fdb\u5165\u5468\u62a5\u7684\u98ce\u683c\u6837\u672c\u3002')
    store.set_intent(user, other["id"], {"workflow": "journal", "goal": '\u65e5\u8bb0', "source": "user"})
    anchors = style_anchors.entries(user, store.get_note(user, note["id"]), "weekly")
    assert anchors[0] == same
    assert any('\u540c\u4e00\u5de5\u4f5c\u6d41' in x for x in anchors)
    assert not any('\u522b\u7684\u4f53\u88c1' in x for x in anchors)


def _state(content: str) -> State:
    return State(mode=modes.for_run(modes.NOTE),
                 ctx=ToolContext(user="u", note_id="n"), content=content)


def test_only_located_feedback_starts_revision():
    st = _state('\u7b2c\u4e00\u6bb5\u5177\u4f53\u6b63\u6587\u3002\n\n\u7b2c\u4e8c\u6bb5\u5177\u4f53\u6b63\u6587\u3002')
    st.ev = Evaluation({"prose_quality": DimensionScore(1, '\u884c\u6587\u8fd8\u53ef\u4ee5\u66f4\u81ea\u7136')},
                       "continue", weakest="prose_quality")
    assert actionable_revision(st) is False
    st.ev = Evaluation({"prose_quality": DimensionScore(1, '\u8bf7\u4fee\u6539\u300c\u7b2c\u4e8c\u6bb5\u5177\u4f53\u6b63\u6587\u300d')},
                       "continue", weakest="prose_quality")
    assert actionable_revision(st) is True


def test_unlocated_cleanup_stops_instead_of_burning_another_round():
    st = _state('\u7b2c\u4e00\u6bb5\u5177\u4f53\u6b63\u6587\u3002')
    st.bag["cleanup_only"] = True
    st.ev = Evaluation({"prose_quality": DimensionScore(1, '\u884c\u6587\u8fd8\u53ef\u4ee5\u66f4\u81ea\u7136')},
                       "continue", weakest="prose_quality")
    assert modes.no_actionable_repair(st) == "no_actionable_revision"
