"""Doc intent (docs/agent-native-editor.md section 3.1): every note knows what it is for.

Goal / audience / done criteria live in `notes.intent` (JSON) and are managed by the
editor's "writing mode". **Every AI action on the note (skeleton / continue / rewrite /
polish / expand / verify / layout) puts it in the first paragraph of the system prompt**:
polish finally knows who the note is for, verify checks against the done criteria.

Pure functions only:
  normalize()   any input -> {goal, reader, done, workflow, source, checked} (one line per field, capped)
  as_text()     the fields joined into one sentence. The frontend `util/docIntent.ts` `intentText`
                emits the same format and sends it with every request (routes without a note_id --
                skeleton / continue / rewrite -- cannot read the stored copy).
  block()       the system-prompt paragraph; empty intent = empty string (not one extra word).

Shared text format (frontend and backend, verbatim):
    Workflow: <id>; Goal: ...; Audience: ...; Done: ...
The legacy format produced before the English-first flip used the Chinese labels and the
fullwidth separator; the parsers below still accept it so older clients and stored text keep
working, but nothing emits it any more.
"""

from __future__ import annotations

from ..util.i18n_zh import ZH

FIELDS = ("goal", "reader", "done")
FIELD_LABEL = {"goal": "Goal", "reader": "Audience", "done": "Done"}
WORKFLOW_FIELD = "Workflow"
# Workflow id <-> human label. The frontend `util/docIntent.ts` WORKFLOW_LABEL is the same
# table. The first four are single-template workflows (one Recipe each in
# `harness/workflows.py`); the rest are template categories whose templates share one
# Recipe, with the sections coming from each template's own scaffold.
WORKFLOW_LABEL = {
    "daily": "Daily report", "weekly": "Weekly report", "journal": "Journal", "meeting": "Meeting notes",
    "reports": "Reports", "meetings": "Meetings", "product": "Product", "research": "Research",
    "writing": "Writing", "personal": "Personal", "sales": "Sales & marketing", "engineering": "Engineering",
    "people": "People", "learning": "Learning & teaching", "ops": "Operations & finance",
}
WORKFLOW_BY_LABEL = {label: key for key, label in WORKFLOW_LABEL.items()}
# Legacy (pre-flip) labels: the Chinese translations of the same labels.
_LEGACY_WORKFLOW_BY_LABEL = {ZH[label]: key for key, label in WORKFLOW_LABEL.items() if label in ZH}
_LEGACY_FIELD_LABEL = {k: ZH[v] for k, v in FIELD_LABEL.items() if v in ZH}
_LEGACY_WORKFLOW_FIELD = ZH.get(WORKFLOW_FIELD, WORKFLOW_FIELD)
SEP = "; "
# Legacy separators / colon: fullwidth semicolon U+FF1B and fullwidth colon U+FF1A.
_LEGACY_SEP = "\uff1b"
_LEGACY_COLON = "\uff1a"
# Per-field cap, same as the frontend INTENT_FIELD_MAX (English text needs about 1.5x the room of Chinese).
FIELD_MAX = 300
# `prefill` only exists for old data; the product only stores user intents (typed, or formed
# by choosing a workflow).
SOURCES = ("", "prefill", "user")
# How many "done" items can be ticked (a sentence does not split into more; keeps junk out)
CHECKED_MAX = 20

# First sentence of the system paragraph. **Say it is a premise**: the model reads a constraint,
# not background.
HEAD = "What this note is for (set by the writer; every action below takes it as a premise): "
# How to use the done criteria: verify / polish check against them, they are not copied.
DONE_HINT = ("The result must satisfy the done criteria; when it does not, say so in the output "
             "instead of pretending. Write in the language of the note and its materials.")


def normalize(raw: object) -> dict:
    """Any shape -> {goal, reader, done, workflow, source, checked}. Fields collapse to one line and
    are capped at FIELD_MAX; source only accepts prefill / user, anything else is empty. A non-dict
    is an empty intent.
    `checked` (P12 section 3.1 "done criteria are checkable"): the done items the user ticked, verbatim.
    Only items code cannot judge need a tick; ticks must survive switching notes, so they are stored
    with the three fields rather than in a separate table. Strings only, de-duplicated, capped at
    CHECKED_MAX."""
    d = raw if isinstance(raw, dict) else {}
    out = {k: " ".join(str(d.get(k) or "").split())[:FIELD_MAX] for k in FIELDS}
    workflow = str(d.get("workflow") or "")
    out["workflow"] = workflow if workflow in WORKFLOW_LABEL else ""
    src = str(d.get("source") or "")
    out["source"] = src if src in SOURCES else ""
    raw_checked = d.get("checked")
    checked: list[str] = []
    if isinstance(raw_checked, list):
        for x in raw_checked:
            s = " ".join(str(x or "").split())[:FIELD_MAX] if isinstance(x, str) else ""
            if s and s not in checked:
                checked.append(s)
            if len(checked) >= CHECKED_MAX:
                break
    out["checked"] = checked
    return out


def is_empty(intent: dict | None) -> bool:
    d = normalize(intent)
    return not (d["goal"] or d["reader"] or d["done"])


def as_text(intent: dict | None) -> str:
    """The one-sentence form the system prompt reads: only the fields that are filled in.
    The workflow label is prepended when a workflow was chosen, but a workflow alone (no visible
    task) is not an intent -- it would be a hidden task the user cannot see."""
    d = normalize(intent)
    # Old versions auto-filled a ``source=prefill`` task from the title. The frontend now treats
    # that history as an empty task; the backend must ignore it too, otherwise the UI shows nothing
    # while the Harness quietly executes it from the database.
    if d["source"] == "prefill" or is_empty(d):
        return ""
    parts = [f"{WORKFLOW_FIELD}: {d['workflow']}"] if d["workflow"] else []
    parts += [f"{FIELD_LABEL[k]}: {d[k]}" for k in FIELDS if d[k]]
    return SEP.join(parts)


def _parts(text: str) -> list[str]:
    out: list[str] = []
    for chunk in (text or "").replace(_LEGACY_SEP, ";").split(";"):
        s = chunk.strip()
        if s:
            out.append(s)
    return out


def _value(part: str, label: str) -> str | None:
    """`part` is `Label: value` (ASCII or legacy fullwidth colon) -> value, else None."""
    for colon in (":", _LEGACY_COLON):
        head = f"{label}{colon}"
        if part.startswith(head):
            return part[len(head):].strip()
    return None


def workflow_of(text: str) -> str:
    """Stable workflow id from the shared text (`Workflow: daily`). Accepts the id, the English
    label and the legacy Chinese label; anything else means no template rules."""
    for part in _parts(text):
        for field in (WORKFLOW_FIELD, _LEGACY_WORKFLOW_FIELD):
            value = _value(part, field)
            if value is None:
                continue
            if value in WORKFLOW_LABEL:
                return value
            if value in WORKFLOW_BY_LABEL:
                return WORKFLOW_BY_LABEL[value]
            if value in _LEGACY_WORKFLOW_BY_LABEL:
                return _LEGACY_WORKFLOW_BY_LABEL[value]
    return ""


def done_of(text: str) -> str:
    """The done criteria back out of the `as_text()` sentence (the harness `ctx.intent` only carries
    that sentence; P13 #1). Done is the last field, so it runs to the end of the text; semicolons
    inside it separate its own items and stay as they are."""
    t = text or ""
    for label in (FIELD_LABEL["done"], _LEGACY_FIELD_LABEL.get("done", "")):
        if not label:
            continue
        for colon in (":", _LEGACY_COLON):
            head = f"{label}{colon}"
            i = t.find(head)
            if i >= 0:
                return t[i + len(head):].strip()
    return ""


def goal_of(text: str) -> str:
    """The user's goal from the stable `as_text` format. Skeleton and body length play no part."""
    for part in _parts(text):
        for label in (FIELD_LABEL["goal"], _LEGACY_FIELD_LABEL.get("goal", "")):
            if not label:
                continue
            value = _value(part, label)
            if value is not None:
                return value
    return ""


def block(text: str) -> str:
    """First paragraph of the system prompt. `text` is the `as_text()` sentence (sent by the
    frontend); empty = nothing added."""
    # Three visible fields of FIELD_MAX chars each plus a short workflow label: enough room, while the
    # body cannot pose as intent.
    t = " ".join((text or "").split())[:FIELD_MAX * 4 + 40]
    if not t:
        return ""
    return f"{HEAD}{t}\n{DONE_HINT}\n\n"
