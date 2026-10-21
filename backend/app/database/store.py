"""SQLite persistence for notes, branches, settings, citations, writing runs and revisions. Preserve user-scoped identifiers across reversible operations."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .wordcount import word_count
from ..editor import intent as intent_mod
from ..util.config import get_settings

_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS notes (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT '',
    pinned      INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS meta (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS note_citations (
    note_id  TEXT NOT NULL,
    fact_id  TEXT NOT NULL,
    user_id  TEXT NOT NULL,
    PRIMARY KEY (note_id, fact_id)
);
CREATE INDEX IF NOT EXISTS idx_citations_fact ON note_citations(user_id, fact_id);

CREATE TABLE IF NOT EXISTS note_tray (
    id        TEXT PRIMARY KEY,
    user_id   TEXT NOT NULL,
    note_id   TEXT NOT NULL,
    kind      TEXT NOT NULL,
    ref_id    TEXT NOT NULL DEFAULT '',
    title     TEXT NOT NULL DEFAULT '',
    excerpt   TEXT NOT NULL DEFAULT '',
    position  INTEGER NOT NULL DEFAULT 0,
    added_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tray_note ON note_tray(user_id, note_id, position);

CREATE TABLE IF NOT EXISTS branches (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    note_id         TEXT NOT NULL,
    parent_note_id  TEXT NOT NULL,
    position        INTEGER NOT NULL DEFAULT 0,
    is_expanded     INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    UNIQUE(note_id, parent_note_id)
);
CREATE INDEX IF NOT EXISTS idx_branches_parent
    ON branches(user_id, parent_note_id, position);
CREATE INDEX IF NOT EXISTS idx_branches_note ON branches(note_id);

CREATE TABLE IF NOT EXISTS skill_config (
    user_id TEXT NOT NULL,
    slug    TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    scopes  TEXT NOT NULL DEFAULT '',
    sandbox TEXT NOT NULL DEFAULT 'none',
    source  TEXT NOT NULL DEFAULT 'user',

    idx     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, slug)
);

CREATE TABLE IF NOT EXISTS writing_plans (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,

    parent_note_id TEXT NOT NULL,
    goal        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active',
    doc_note_id TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS writing_sections (
    id          TEXT PRIMARY KEY,
    plan_id     TEXT NOT NULL,
    idx         INTEGER NOT NULL,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    note_id     TEXT NOT NULL DEFAULT '',
    summary     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_writing_sections_plan ON writing_sections(plan_id, idx);

CREATE TABLE IF NOT EXISTS ingest_jobs (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    status      TEXT NOT NULL,
    facts       INTEGER NOT NULL DEFAULT 0,
    detail      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    cancel_requested INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ingest_items (
    id          TEXT PRIMARY KEY,
    job_id      TEXT NOT NULL,
    idx         INTEGER NOT NULL,
    filename    TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'queued',
    facts       INTEGER NOT NULL DEFAULT 0,
    detail      TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_job ON ingest_items(job_id, idx);

CREATE TABLE IF NOT EXISTS harness_snapshots (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    note_id    TEXT NOT NULL DEFAULT '',
    mode       TEXT NOT NULL,
    round      INTEGER NOT NULL DEFAULT 0,
    state      TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_user ON harness_snapshots(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS llm_usage (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           TEXT NOT NULL DEFAULT '',
    feature           TEXT NOT NULL DEFAULT '',
    model             TEXT NOT NULL DEFAULT '',
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    ms                INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_user_time ON llm_usage(user_id, created_at);

CREATE TABLE IF NOT EXISTS note_trash (
    user_id     TEXT NOT NULL,
    note_id     TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    chars       INTEGER NOT NULL DEFAULT 0,
    payload     TEXT NOT NULL,
    deleted_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, note_id)
);

CREATE TABLE IF NOT EXISTS note_remotes (
    user_id     TEXT NOT NULL,
    note_id     TEXT NOT NULL,
    platform    TEXT NOT NULL,
    remote_id   TEXT NOT NULL DEFAULT '',
    remote_path TEXT NOT NULL DEFAULT '',
    exported_at TEXT NOT NULL,
    remote_rev  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, note_id, platform)
);

CREATE TABLE IF NOT EXISTS kb_entity_merges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    code_a      TEXT NOT NULL,
    code_b      TEXT NOT NULL,
    decision    TEXT NOT NULL,
    why         TEXT NOT NULL DEFAULT '',
    decided_at  TEXT NOT NULL,
    UNIQUE (user_id, code_a, code_b)
);

CREATE TABLE IF NOT EXISTS kb_conflicts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    new_fact_id TEXT NOT NULL,
    old_fact_id TEXT NOT NULL,
    unit        TEXT NOT NULL DEFAULT '',
    say         TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'open',
    resolution  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE (user_id, new_fact_id, old_fact_id)
);

CREATE TABLE IF NOT EXISTS note_revisions (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    note_id    TEXT NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    content    TEXT NOT NULL DEFAULT '',
    reason     TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_revisions_note ON note_revisions(user_id, note_id, created_at DESC);

CREATE TABLE IF NOT EXISTS note_change_layers (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    note_id     TEXT NOT NULL,
    label       TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'other',
    run_id      TEXT NOT NULL DEFAULT '',
    round_no    INTEGER NOT NULL DEFAULT 0,
    seq         INTEGER NOT NULL DEFAULT 0,
    state       TEXT NOT NULL DEFAULT 'on',
    at          TEXT NOT NULL DEFAULT '',
    content_tag TEXT NOT NULL DEFAULT '',
    hunks       TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_change_layers_note ON note_change_layers(user_id, note_id, seq);

CREATE TABLE IF NOT EXISTS writing_feedback (
    user_id    TEXT NOT NULL,
    note_id    TEXT NOT NULL,
    layer_id   TEXT NOT NULL,
    hunk_key   INTEGER NOT NULL,
    run_id     TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT 'other',
    label      TEXT NOT NULL DEFAULT '',
    decision   TEXT NOT NULL,
    del_text   TEXT NOT NULL DEFAULT '',
    ins_text   TEXT NOT NULL DEFAULT '',
    decided_at TEXT NOT NULL,
    PRIMARY KEY (user_id, note_id, layer_id, hunk_key)
);
CREATE INDEX IF NOT EXISTS idx_writing_feedback_note
    ON writing_feedback(user_id, note_id, decided_at DESC);

CREATE TABLE IF NOT EXISTS user_profile (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profile_user ON user_profile(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS provider_credentials (
    provider   TEXT PRIMARY KEY,
    api_key    TEXT NOT NULL DEFAULT '',
    model      TEXT NOT NULL DEFAULT '',
    base_url   TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_config (
    id           TEXT PRIMARY KEY,
    provider     TEXT NOT NULL DEFAULT 'local',
    gpt_api_key  TEXT NOT NULL DEFAULT '',
    gpt_model    TEXT NOT NULL DEFAULT 'gpt-4.1-mini',
    gpt_base_url TEXT NOT NULL DEFAULT 'https://api.openai.com/v1',
    asr_base_url TEXT NOT NULL DEFAULT '',
    auto_sync_notes INTEGER NOT NULL DEFAULT 0,

    local_base_url TEXT NOT NULL DEFAULT '',
    local_model    TEXT NOT NULL DEFAULT '',
    local_api_key  TEXT NOT NULL DEFAULT '',

    vision_base_url TEXT NOT NULL DEFAULT '',
    vision_model    TEXT NOT NULL DEFAULT '',
    vision_api_key  TEXT NOT NULL DEFAULT '',

    asr_provider         TEXT NOT NULL DEFAULT '',
    assemblyai_api_key   TEXT NOT NULL DEFAULT '',
    assemblyai_region    TEXT NOT NULL DEFAULT '',
    speechmatics_api_key TEXT NOT NULL DEFAULT '',
    speechmatics_region  TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS harness_runs (
    id              TEXT PRIMARY KEY,
    key             TEXT NOT NULL,
    status          TEXT NOT NULL,
    rounds          INTEGER NOT NULL,
    final_scores    TEXT NOT NULL,
    weak_dimensions TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_harness_runs_key ON harness_runs(key, created_at DESC);

CREATE TABLE IF NOT EXISTS harness_rounds (
    id           TEXT PRIMARY KEY,
    key          TEXT NOT NULL,
    run_id       TEXT NOT NULL DEFAULT '',
    round        INTEGER NOT NULL,
    scores       TEXT NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT '',
    weakest      TEXT NOT NULL DEFAULT '',
    content_len  INTEGER NOT NULL DEFAULT 0,
    facts_new    INTEGER NOT NULL DEFAULT 0,
    facts_total  INTEGER NOT NULL DEFAULT 0,
    tool_calls   INTEGER NOT NULL DEFAULT 0,
    repeat_calls INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_harness_rounds_run ON harness_rounds(run_id, round);
CREATE INDEX IF NOT EXISTS idx_harness_rounds_key ON harness_rounds(key, created_at DESC);

CREATE TABLE IF NOT EXISTS harness_edits (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    note_id      TEXT NOT NULL,
    run_id       TEXT NOT NULL DEFAULT '',
    key          TEXT NOT NULL DEFAULT '',
    revision_id  TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'open',
    base_chars   INTEGER NOT NULL DEFAULT 0,
    ai_chars     INTEGER NOT NULL DEFAULT 0,
    user_chars   INTEGER NOT NULL DEFAULT 0,
    kept_chars   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    edited_at    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_harness_edits_note ON harness_edits(user_id, note_id, status);
"""


_TERMINAL_ITEM_STATUSES = {"done", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db_path() -> Path:
    root = Path(get_settings().kite_data_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / "notes.sqlite3"


def _add_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


_ADDED_COLUMNS = (
    ("ingest_jobs", "cancel_requested", "INTEGER NOT NULL DEFAULT 0"),


    ("llm_usage", "cached_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("llm_usage", "cache_write_tokens", "INTEGER NOT NULL DEFAULT 0"),


    ("harness_runs", "stopped", "TEXT NOT NULL DEFAULT ''"),


    ("harness_rounds", "cached_calls", "INTEGER NOT NULL DEFAULT 0"),


    ("harness_rounds", "superseded", "INTEGER NOT NULL DEFAULT 0"),


    ("harness_rounds", "revisions_proposed", "INTEGER NOT NULL DEFAULT 0"),
    ("harness_rounds", "revisions_dropped", "INTEGER NOT NULL DEFAULT 0"),


    ("harness_rounds", "depth_dropped", "INTEGER NOT NULL DEFAULT 0"),

    ("note_remotes", "remote_rev", "TEXT NOT NULL DEFAULT ''"),


    ("harness_rounds", "claim_atoms", "INTEGER NOT NULL DEFAULT -1"),


    ("harness_rounds", "fired_checks", "TEXT NOT NULL DEFAULT ''"),


    ("harness_rounds", "abstained", "TEXT NOT NULL DEFAULT ''"),


    ("harness_rounds", "cite_located", "INTEGER NOT NULL DEFAULT -1"),
    ("harness_rounds", "cite_marked", "INTEGER NOT NULL DEFAULT -1"),
    ("harness_rounds", "cite_matched", "INTEGER NOT NULL DEFAULT -1"),


    ("harness_runs", "tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("harness_runs", "calls", "INTEGER NOT NULL DEFAULT 0"),

    ("note_revisions", "run_id", "TEXT NOT NULL DEFAULT ''"),


    ("note_revisions", "round_no", "INTEGER NOT NULL DEFAULT 0"),
    ("notes", "pinned", "INTEGER NOT NULL DEFAULT 0"),


    ("notes", "icon", "TEXT NOT NULL DEFAULT ''"),


    ("notes", "spine", "TEXT NOT NULL DEFAULT ''"),
    ("notes", "beats", "TEXT NOT NULL DEFAULT ''"),


    ("notes", "intent", "TEXT NOT NULL DEFAULT ''"),


    ("skill_config", "idx", "INTEGER NOT NULL DEFAULT 0"),


    ("skill_config", "seeded_sha", "TEXT NOT NULL DEFAULT ''"),


    ("notes", "ingested_at", "TEXT NOT NULL DEFAULT ''"),


    ("provider_config", "asr_base_url", "TEXT NOT NULL DEFAULT ''"),

    ("provider_config", "auto_sync_notes", "INTEGER NOT NULL DEFAULT 0"),

    ("provider_config", "local_base_url", "TEXT NOT NULL DEFAULT ''"),
    ("provider_config", "local_model", "TEXT NOT NULL DEFAULT ''"),
    ("provider_config", "local_api_key", "TEXT NOT NULL DEFAULT ''"),
    ("provider_config", "vision_base_url", "TEXT NOT NULL DEFAULT ''"),
    ("provider_config", "vision_model", "TEXT NOT NULL DEFAULT ''"),
    ("provider_config", "vision_api_key", "TEXT NOT NULL DEFAULT ''"),
    # Hosted speech-to-text providers (AssemblyAI / Speechmatics) next to the whisper.cpp server.
    ("provider_config", "asr_provider", "TEXT NOT NULL DEFAULT ''"),
    ("provider_config", "assemblyai_api_key", "TEXT NOT NULL DEFAULT ''"),
    ("provider_config", "assemblyai_region", "TEXT NOT NULL DEFAULT ''"),
    ("provider_config", "speechmatics_api_key", "TEXT NOT NULL DEFAULT ''"),
    ("provider_config", "speechmatics_region", "TEXT NOT NULL DEFAULT ''"),


    ("ingest_items", "chunks_total", "INTEGER NOT NULL DEFAULT 0"),
    ("ingest_items", "chunks_done", "INTEGER NOT NULL DEFAULT 0"),


    ("ingest_items", "note_id", "TEXT NOT NULL DEFAULT ''"),
    ("ingest_jobs", "payload_path", "TEXT NOT NULL DEFAULT ''"),
    ("ingest_jobs", "chunk_ms", "INTEGER NOT NULL DEFAULT 0"),
    ("ingest_jobs", "chunks_done", "INTEGER NOT NULL DEFAULT 0"),
    ("ingest_jobs", "chunks_total", "INTEGER NOT NULL DEFAULT 0"),
    ("ingest_jobs", "chars_done", "INTEGER NOT NULL DEFAULT 0"),
    ("ingest_jobs", "started_at", "TEXT NOT NULL DEFAULT ''"),


    ("notes", "source", "TEXT NOT NULL DEFAULT ''"),
    ("notes", "source_id", "TEXT NOT NULL DEFAULT ''"),
    ("notes", "source_sha", "TEXT NOT NULL DEFAULT ''"),
    ("notes", "imported_at", "TEXT NOT NULL DEFAULT ''"),
)


ROOT_ID = "root"


def _drop_orphans(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM note_citations WHERE note_id NOT IN (SELECT id FROM notes)")
    conn.execute("DELETE FROM note_revisions WHERE note_id NOT IN (SELECT id FROM notes)")
    conn.execute("DELETE FROM harness_snapshots WHERE note_id<>'' AND note_id NOT IN (SELECT id FROM notes)")
    conn.execute("DELETE FROM harness_runs WHERE key LIKE 'note:%' AND substr(key, 6) NOT IN (SELECT id FROM notes)")
    conn.execute("DELETE FROM harness_edits WHERE note_id NOT IN (SELECT id FROM notes)")
    conn.execute("DELETE FROM note_change_layers WHERE note_id NOT IN (SELECT id FROM notes)")
    conn.execute("DELETE FROM writing_feedback WHERE note_id NOT IN (SELECT id FROM notes)")


def _drop_orphan_runs(conn: sqlite3.Connection) -> None:
    conn.execute(
        "DELETE FROM harness_runs WHERE "
        "(CASE WHEN instr(key, ':') > 0 THEN substr(key, instr(key, ':') + 1) ELSE key END) "
        "NOT IN (SELECT id FROM notes)")


def _prune_runs(conn: sqlite3.Connection) -> None:
    conn.execute(
        "DELETE FROM harness_runs WHERE rowid NOT IN ("
        " SELECT rowid FROM ("
        "  SELECT rowid, ROW_NUMBER() OVER (PARTITION BY key ORDER BY created_at DESC, rowid DESC) AS rn"
        "  FROM harness_runs) WHERE rn <= 50)")


def _migrate_once(conn: sqlite3.Connection, key: str, run) -> bool:
    done = conn.execute("SELECT 1 FROM meta WHERE key=?", (key,)).fetchone()
    if done:
        return False
    run(conn)
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                 (key, _now()))
    conn.commit()
    return True


def _folders_into_tree(conn: sqlite3.Connection) -> None:
    has_folders = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='folders'"
    ).fetchone()
    folders = conn.execute(
        "SELECT id, user_id, name, created_at FROM folders").fetchall() \
        if has_folders else []
    for f in folders:

        if conn.execute("SELECT 1 FROM notes WHERE id=?", (f["id"],)).fetchone():
            continue
        conn.execute(
            "INSERT INTO notes (id, user_id, title, content, pinned, folder_id,"
            " created_at, updated_at) VALUES (?,?,?,'',0,NULL,?,?)",
            (f["id"], f["user_id"], f["name"], f["created_at"], f["created_at"]))


    note_cols = {r[1] for r in conn.execute("PRAGMA table_info(notes)")}
    col = "folder_id" if "folder_id" in note_cols else "NULL AS folder_id"
    notes = conn.execute(
        f"SELECT id, user_id, {col}, created_at FROM notes").fetchall()
    seen: dict[tuple[str, str], int] = {}
    for n in notes:
        parent = n["folder_id"] or ROOT_ID
        key = (n["user_id"], parent)
        pos = seen.get(key, 0)
        seen[key] = pos + 1
        conn.execute(
            "INSERT OR IGNORE INTO branches (id, user_id, note_id,"
            " parent_note_id, position, is_expanded, created_at)"
            " VALUES (?,?,?,?,?,0,?)",
            (uuid.uuid4().hex[:12], n["user_id"], n["id"], parent, pos,
             n["created_at"]))


def _drop_folder_remnants(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(notes)")}
    if "folder_id" in cols:
        conn.execute("DROP INDEX IF EXISTS idx_notes_folder")
        conn.execute("ALTER TABLE notes DROP COLUMN folder_id")
    conn.execute("DROP INDEX IF EXISTS idx_folders_user")
    conn.execute("DROP TABLE IF EXISTS folders")


def _plan_folder_to_parent(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(writing_plans)")}
    if "folder_id" in cols and "parent_note_id" not in cols:
        conn.execute("ALTER TABLE writing_plans RENAME COLUMN folder_id"
                     " TO parent_note_id")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    for table, column, decl in _ADDED_COLUMNS:
        _add_column(conn, table, column, decl)


    _migrate_once(conn, "folders-into-tree-v1", _folders_into_tree)
    _migrate_once(conn, "plan-folder-to-parent-v1", _plan_folder_to_parent)
    _migrate_once(conn, "drop-folder-remnants-v1", _drop_folder_remnants)
    _migrate_once(conn, "drop-orphans-v1", _drop_orphans)
    _migrate_once(conn, "prune-runs-v1", _prune_runs)
    _migrate_once(conn, "drop-orphan-runs-v2", _drop_orphan_runs)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_writing_plans_parent"
                 " ON writing_plans(user_id, parent_note_id, status)")
    return conn


def _note(row) -> dict:
    d = dict(row)
    try:
        d["beats"] = json.loads(d.get("beats") or "[]")
    except (TypeError, ValueError):
        d["beats"] = []
    if not isinstance(d["beats"], list):
        d["beats"] = []
    d["spine"] = d.get("spine") or ""

    try:
        raw = json.loads(d.get("intent") or "{}")
    except (TypeError, ValueError):
        raw = {}
    d["intent"] = intent_mod.normalize(raw)
    return d


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


PREVIEW_CHARS = 80
BRIEF_MAX = 50
_MD_MARK = re.compile(r"^\s*(#{1,6}|[-*>]|\d+\.)\s+", re.M)


def match_snippet(content: str, query: str, span: int = 40, before: int = 18) -> dict | None:
    q = (query or "").strip()
    if not q:
        return None
    text = re.sub(r"\s+", " ", _MD_MARK.sub("", content or ""))
    i = text.lower().find(q.lower())
    if i < 0:
        return None
    start, end = max(0, i - before), min(len(text), i + len(q) + span)
    return {"before": ("…" if start > 0 else "") + text[start:i], "hit": text[i:i + len(q)],
            "after": text[i + len(q):end] + ("…" if end < len(text) else "")}


def _first_body_line(content: str, title: str = "", limit: int = 60) -> str:
    lines = [ln.strip() for ln in (content or "").split("\n")[:60]]
    clean = lambda s: re.sub(r"[*_`\[\]]", "", re.sub(r"^([-*>+]|\d+\.|#{1,6})\s*", "", s)).strip()   # noqa: E731
    shown = (title or "").strip()
    if shown in ("", '\u672a\u547d\u540d', "Untitled", "note"):
        shown = next((clean(ln) for ln in lines if ln), "")
    body, heads = [], []
    fenced = False
    for s in lines:
        if s.startswith("```"):
            fenced = not fenced
            continue
        if fenced or not s or s.startswith("!["):
            continue
        c = clean(s)
        if len(c) <= 1 or c.lower() == shown.lower():
            continue
        (heads if s.startswith("#") else body).append(c)
    pick = body[0] if body else (heads[0] if heads else "")
    return pick[:limit]


def list_notes_brief(user_id: str, q: str = "") -> dict:
    with connect() as c:
        if q:
            like = _like(q)
            rows = c.execute(
                "SELECT id, title, updated_at, pinned, icon, content FROM notes WHERE user_id=? AND "
                "(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\') ORDER BY pinned DESC, updated_at DESC",
                (user_id, like, like)).fetchall()
        else:
            rows = c.execute(
                "SELECT id, title, updated_at, pinned, icon, substr(content, 1, ?) AS content, "
                "length(trim(content)) > 0 AS has_body FROM notes WHERE user_id=? ORDER BY pinned DESC, updated_at DESC",
                (PREVIEW_CHARS * 8, user_id)).fetchall()
    out = []
    for r in rows[:BRIEF_MAX]:
        content = r["content"] or ""
        d = {"id": r["id"], "title": r["title"] or "", "updated_at": r["updated_at"], "pinned": bool(r["pinned"]), "icon": r["icon"] or "",
             "preview": content[:PREVIEW_CHARS], "has_body": bool(r["has_body"]) if "has_body" in r.keys() else bool(content.strip()),
             "first_body": _first_body_line(content, r["title"] or ""), "snippet": None}
        if q and q.lower() not in (r["title"] or "").lower():
            d["snippet"] = match_snippet(content, q)
        out.append(d)
    return {"notes": out, "total": len(rows)}


def list_notes(user_id: str, q: str = "") -> list[dict]:
    with connect() as c:
        if q:
            like = _like(q)
            rows = c.execute(
                "SELECT * FROM notes WHERE user_id=? AND (title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\') "
                "ORDER BY pinned DESC, updated_at DESC",
                (user_id, like, like)).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM notes WHERE user_id=? ORDER BY pinned DESC, updated_at DESC",
                (user_id,)).fetchall()
    return [_note(r) for r in rows]


def get_note(user_id: str, note_id: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM notes WHERE user_id=? AND id=?",
                        (user_id, note_id)).fetchone()
    return _note(row) if row else None


def add_conflict(user_id: str, new_fact_id: str, old_fact_id: str, unit: str, say: str, source: str = "") -> bool:
    with connect() as c:
        cur = c.execute("INSERT OR IGNORE INTO kb_conflicts (user_id,new_fact_id,old_fact_id,unit,say,source,created_at) VALUES (?,?,?,?,?,?,?)",
                        (user_id, new_fact_id, old_fact_id, unit, say, source, _now()))
        return cur.rowcount > 0


def record_entity_decision(user_id: str, code_a: str, code_b: str, decision: str,
                           why: str = "") -> None:
    a, b = (code_a, code_b) if code_a <= code_b else (code_b, code_a)
    with connect() as c:
        c.execute("INSERT INTO kb_entity_merges (user_id,code_a,code_b,decision,why,decided_at)"
                  " VALUES (?,?,?,?,?,?)"
                  " ON CONFLICT(user_id,code_a,code_b) DO UPDATE SET decision=excluded.decision,"
                  " why=excluded.why, decided_at=excluded.decided_at",
                  (user_id, a, b, decision, why, _now()))


def entity_decisions(user_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT code_a,code_b,decision,why,decided_at FROM kb_entity_merges"
                         " WHERE user_id=? ORDER BY id", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def forget_entity_decision(user_id: str, code_a: str, code_b: str) -> bool:
    a, b = (code_a, code_b) if code_a <= code_b else (code_b, code_a)
    with connect() as c:
        return c.execute("DELETE FROM kb_entity_merges WHERE user_id=? AND code_a=? AND code_b=?",
                         (user_id, a, b)).rowcount > 0


def list_conflicts(user_id: str, status: str = "open", limit: int = 100) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM kb_conflicts WHERE user_id=? AND status=? ORDER BY id DESC LIMIT ?",
                         (user_id, status, limit)).fetchall()
    return [dict(r) for r in rows]


def count_open_conflicts(user_id: str) -> int:
    with connect() as c:
        return int(c.execute("SELECT COUNT(*) FROM kb_conflicts WHERE user_id=? AND status='open'", (user_id,)).fetchone()[0])


def resolve_conflict(user_id: str, conflict_id: int, resolution: str) -> dict | None:
    with connect() as c:
        c.execute("UPDATE kb_conflicts SET status='resolved', resolution=? WHERE user_id=? AND id=?",
                  (resolution, user_id, conflict_id))
        row = c.execute("SELECT * FROM kb_conflicts WHERE user_id=? AND id=?", (user_id, conflict_id)).fetchone()
    return dict(row) if row else None


def drop_conflicts_for_facts(user_id: str, fact_ids: set[str]) -> int:
    if not fact_ids:
        return 0
    ids = list(fact_ids)
    with connect() as c:
        n = 0
        for i in range(0, len(ids), 400):
            part = ids[i:i + 400]
            q = ",".join("?" * len(part))
            n += c.execute(f"DELETE FROM kb_conflicts WHERE user_id=? AND (new_fact_id IN ({q}) OR old_fact_id IN ({q}))",
                           [user_id, *part, *part]).rowcount
        return n


def record_remote(user_id: str, note_id: str, platform: str, remote_id: str = "", remote_path: str = "", remote_rev: str = "") -> None:
    with connect() as c:
        c.execute("INSERT OR REPLACE INTO note_remotes (user_id,note_id,platform,remote_id,remote_path,exported_at,remote_rev) VALUES (?,?,?,?,?,?,?)",
                  (user_id, note_id, platform, remote_id, remote_path, _now(), remote_rev))


def get_remote(user_id: str, note_id: str, platform: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM note_remotes WHERE user_id=? AND note_id=? AND platform=?",
                        (user_id, note_id, platform)).fetchone()
    return dict(row) if row else None


def list_remotes(user_id: str, note_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM note_remotes WHERE user_id=? AND note_id=? ORDER BY platform",
                         (user_id, note_id)).fetchall()
    return [dict(r) for r in rows]


def content_sha(content: str) -> str:
    import hashlib
    return hashlib.sha1(content.encode("utf-8")).hexdigest()[:16]


def find_note_by_source(user_id: str, source: str, source_id: str) -> dict | None:
    if not source or not source_id:
        return None
    with connect() as c:
        row = c.execute("SELECT * FROM notes WHERE user_id=? AND source=? AND source_id=? ORDER BY created_at LIMIT 1",
                        (user_id, source, source_id)).fetchone()
    return _note(row) if row else None


def set_note_source(user_id: str, note_id: str, source: str, source_id: str, sha: str) -> None:
    with connect() as c:
        c.execute("UPDATE notes SET source=?, source_id=?, source_sha=?, imported_at=? WHERE id=? AND user_id=?",
                  (source, source_id, sha, _now(), note_id, user_id))


def update_note_from_source(user_id: str, note_id: str, title: str, content: str, sha: str) -> None:
    with connect() as c:
        c.execute("UPDATE notes SET title=?, content=?, source_sha=?, imported_at=?, updated_at=? WHERE id=? AND user_id=?",
                  (title, content, sha, _now(), _now(), note_id, user_id))
    sync_citations(user_id, note_id, content)


def create_note(user_id: str, title: str, content: str,
                parent_id: str = ROOT_ID, *, source: str = "") -> dict:
    note = {"id": uuid.uuid4().hex[:12], "user_id": user_id, "title": title,
            "content": content, "pinned": 0, "source": source,
            "created_at": _now(), "updated_at": _now()}
    with connect() as c:
        c.execute(
            "INSERT INTO notes (id,user_id,title,content,pinned,source,created_at,updated_at) "
            "VALUES (:id,:user_id,:title,:content,:pinned,:source,:created_at,:updated_at)", note)
        pos = _next_position(c, user_id, parent_id)
        c.execute("INSERT INTO branches (id,user_id,note_id,parent_note_id,"
                  "position,is_expanded,created_at) VALUES (?,?,?,?,?,0,?)",
                  (uuid.uuid4().hex[:12], user_id, note["id"], parent_id, pos,
                   note["created_at"]))
        c.commit()


    if content:
        sync_citations(user_id, note["id"], content)
    return {**note, "spine": "", "beats": []}


REVISION_INTERVAL_S = 600

REVISION_KEEP = 100


def _snapshot_locked(c: sqlite3.Connection, user_id: str, note_id: str, title: str,
                     content: str, reason: str, *, force: bool,
                     run_id: str = "", round_no: int = 0) -> str:
    if not (content or "").strip():
        return ""
    if not force:
        last = c.execute(
            "SELECT created_at FROM note_revisions WHERE user_id=? AND note_id=?"
            " ORDER BY created_at DESC, rowid DESC LIMIT 1", (user_id, note_id)).fetchone()
        if last:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(last["created_at"])).total_seconds()
            if age < REVISION_INTERVAL_S:
                return ""
    rev_id = uuid.uuid4().hex[:12]
    c.execute("INSERT INTO note_revisions (id,user_id,note_id,title,content,reason,run_id,round_no,created_at)"
              " VALUES (?,?,?,?,?,?,?,?,?)",
              (rev_id, user_id, note_id, title, content, reason, run_id, int(round_no or 0), _now()))
    c.execute("DELETE FROM note_revisions WHERE user_id=? AND note_id=? AND id NOT IN ("
              "SELECT id FROM note_revisions WHERE user_id=? AND note_id=?"
              " ORDER BY created_at DESC, rowid DESC LIMIT ?)",
              (user_id, note_id, user_id, note_id, REVISION_KEEP))
    return rev_id


EDIT_SOURCES = ("user", "harness", "import")


def update_note(user_id: str, note_id: str, title: str, content: str,
                *, source: str = "user") -> dict | None:
    if source not in EDIT_SOURCES:
        raise ValueError(f'update_note source must be one of {EDIT_SOURCES}; received {source!r}')
    with connect() as c:
        old = c.execute("SELECT title, content FROM notes WHERE user_id=? AND id=?",
                        (user_id, note_id)).fetchone()
        if not old:
            return None

        if old["content"] != content:
            _snapshot_locked(c, user_id, note_id, old["title"], old["content"], "auto", force=False)
            if source == "user":


                _close_harness_edit_locked(c, user_id, note_id, content)
        cur = c.execute(
            "UPDATE notes SET title=?, content=?, updated_at=? "
            "WHERE user_id=? AND id=?",
            (title, content, _now(), user_id, note_id))
        if cur.rowcount == 0:
            return None


    sync_citations(user_id, note_id, content)
    return get_note(user_id, note_id)


def snapshot_note(user_id: str, note_id: str, reason: str = "manual",
                  *, run_id: str = "", round_no: int = 0) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT title, content FROM notes WHERE user_id=? AND id=?",
                        (user_id, note_id)).fetchone()
        if not row:
            return None
        if not _snapshot_locked(c, user_id, note_id, row["title"], row["content"],
                                reason, force=True, run_id=run_id, round_no=round_no):
            return None
    return list_revisions(user_id, note_id)[0]


def find_run_revision(user_id: str, note_id: str, run_id: str, reason: str) -> str:
    if not run_id:
        return ""
    with connect() as c:
        row = c.execute("SELECT id FROM note_revisions WHERE user_id=? AND note_id=? AND run_id=? AND reason=?"
                        " ORDER BY created_at DESC, rowid DESC LIMIT 1", (user_id, note_id, run_id, reason)).fetchone()
    return str(row["id"]) if row else ""


REVISION_REASON_HARNESS = "harness"


REVISION_REASON_ROUND = "round"


REVISION_REASON_RUN_END = "run_end"


def snapshot_content(user_id: str, note_id: str, title: str, content: str, reason: str,
                     *, run_id: str = "", round_no: int = 0) -> str:
    with connect() as c:
        return _snapshot_locked(c, user_id, note_id, title, content, reason, force=True,
                                run_id=run_id, round_no=round_no)


CHANGE_LAYER_SOURCES = (
    "round",
    "continue",
    "rewrite",
    "polish",
    "expand",
    "format",
    "restructure",
    "voice",
    "table",
    "block",
    "undo_round",
    "other",
)


LAYER_STATES = ("on", "off")


HUNK_STATES = ("pending", "off", "accepted", "reverted")


CHANGE_LAYER_KEEP = 20


CHANGE_LAYER_SETTLED_KEEP = 60


CHANGE_LAYER_MAX_AGE_DAYS = 30


CHANGE_LAYER_HUNKS = 500


def _change_hunk(h: dict, *, index: int) -> dict | None:
    if not isinstance(h, dict):
        return None
    state = str(h.get("state") or "pending")
    if state not in HUNK_STATES:
        return None
    try:
        frm = max(0, int(h.get("from") or 0))
        to = max(frm, int(h.get("to") or 0))
    except (TypeError, ValueError):
        return None
    return {
        "k": int(h.get("k") if isinstance(h.get("k"), int) else index),
        "from": frm,
        "to": to,
        "del": str(h.get("del") or ""),
        "ins": str(h.get("ins") or ""),
        "state": state,
        "soft": bool(h.get("soft")),
        "before": str(h.get("before") or "")[-48:],
        "after": str(h.get("after") or "")[:48],
    }


LIVE_HUNK_STATES = ("pending", "off")


def _layer_is_live(layer: dict) -> bool:
    return any(h.get("state") in LIVE_HUNK_STATES for h in (layer.get("hunks") or []))


def list_change_layers(user_id: str, note_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT * FROM note_change_layers WHERE user_id=? AND note_id=?"
            " ORDER BY seq, created_at, rowid", (user_id, note_id)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["hunks"] = json.loads(d.get("hunks") or "[]")
        except (TypeError, ValueError):
            d["hunks"] = []
        out.append(d)
    return out


def _archive_layer_feedback_locked(c: sqlite3.Connection, user_id: str,
                                   note_id: str, layer: dict, *,
                                   accept_live: bool = False) -> None:
    for i, h in enumerate(layer.get("hunks") or []):
        if h.get("soft"):
            continue
        state = str(h.get("state") or "pending")
        decision = state if state in ("accepted", "reverted") else (
            "accepted" if accept_live and state in LIVE_HUNK_STATES else "")
        if not decision:
            continue
        c.execute(
            "INSERT INTO writing_feedback"
            " (user_id,note_id,layer_id,hunk_key,run_id,source,label,decision,"
            "del_text,ins_text,decided_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(user_id,note_id,layer_id,hunk_key) DO UPDATE SET"
            " run_id=excluded.run_id,source=excluded.source,label=excluded.label,"
            " decision=excluded.decision,del_text=excluded.del_text,"
            " ins_text=excluded.ins_text,decided_at=excluded.decided_at",
            (user_id, note_id, str(layer.get("id") or ""), int(h.get("k", i)),
             str(layer.get("run_id") or ""), str(layer.get("source") or "other"),
             str(layer.get("label") or ""), decision, str(h.get("del") or ""),
             str(h.get("ins") or ""), str(layer.get("at") or "") or _now()))


def writing_feedback(user_id: str, note_id: str, *, limit: int = 16) -> dict:
    with connect() as c:
        rows = c.execute(
            "SELECT * FROM writing_feedback WHERE user_id=? AND note_id=?"
            " ORDER BY decided_at DESC, rowid DESC LIMIT ?",
            (user_id, note_id, max(1, min(int(limit), 50)))).fetchall()
        live = c.execute(
            "SELECT * FROM note_change_layers WHERE user_id=? AND note_id=?"
            " ORDER BY updated_at DESC, rowid DESC", (user_id, note_id)).fetchall()
    items = [dict(r) for r in rows]
    known = {(r["layer_id"], int(r["hunk_key"])) for r in items}


    current: list[dict] = []
    for raw in live:
        layer = dict(raw)
        try:
            hunks = json.loads(layer.get("hunks") or "[]")
        except (TypeError, ValueError):
            hunks = []
        for i, h in enumerate(hunks):
            key = (layer["id"], int(h.get("k", i)))
            if key in known or h.get("soft") or h.get("state") not in ("accepted", "reverted"):
                continue
            current.append({
                "user_id": user_id, "note_id": note_id, "layer_id": layer["id"],
                "hunk_key": key[1], "run_id": layer.get("run_id") or "",
                "source": layer.get("source") or "other", "label": layer.get("label") or "",
                "decision": h["state"], "del_text": h.get("del") or "",
                "ins_text": h.get("ins") or "", "decided_at": layer.get("at") or layer["updated_at"],
            })
    combined = sorted(current + items, key=lambda r: r.get("decided_at") or "", reverse=True)
    items = combined[:limit]
    accepted = sum(r["decision"] == "accepted" for r in items)
    reverted = sum(r["decision"] == "reverted" for r in items)
    latest = {"layer_id": "", "label": "", "accepted": 0, "reverted": 0,
              "decided_at": ""}
    if combined:
        lid = combined[0]["layer_id"]


        with connect() as c:
            archived_latest = [dict(r) for r in c.execute(
                "SELECT * FROM writing_feedback WHERE user_id=? AND note_id=? AND layer_id=?",
                (user_id, note_id, lid)).fetchall()]
        same_by_key = {(r["layer_id"], int(r["hunk_key"])): r
                       for r in archived_latest}
        for r in current:
            if r["layer_id"] == lid:
                same_by_key[(r["layer_id"], int(r["hunk_key"]))] = r
        same = list(same_by_key.values())
        if not same:
            same = [r for r in combined if r["layer_id"] == lid]
        latest = {
            "layer_id": lid, "label": combined[0]["label"],
            "accepted": sum(r["decision"] == "accepted" for r in same),
            "reverted": sum(r["decision"] == "reverted" for r in same),
            "decided_at": combined[0]["decided_at"],
        }
    return {"accepted": accepted, "reverted": reverted,
            "decided": accepted + reverted, "latest": latest, "items": items,
            "run_retention": latest_harness_retention(user_id, note_id),
            "calibration": retention_calibration(user_id)}


def save_change_layers(user_id: str, note_id: str, layers: list[dict]) -> dict:
    evicted: list[dict] = []
    rejected: list[dict] = []
    cleaned: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=CHANGE_LAYER_MAX_AGE_DAYS)
    for i, layer in enumerate(layers or []):
        if not isinstance(layer, dict):
            rejected.append({"label": "", "why": 'Invalid layer structure; not saved'})
            continue
        label = str(layer.get("label") or "")
        raw = layer.get("hunks") or []
        if not isinstance(raw, list):
            rejected.append({"label": label, "why": 'Invalid layer change list; not saved'})
            continue
        if len(raw) > CHANGE_LAYER_HUNKS:
            rejected.append({"label": label,
                             "why": f'This layer has {len(raw)} changes; the retention limit is {CHANGE_LAYER_HUNKS} changes'})
            continue
        hunks = []
        dropped = 0
        for j, h in enumerate(raw):
            one = _change_hunk(h, index=j)
            if one is None:
                dropped += 1
            else:
                hunks.append(one)
        if dropped:
            rejected.append({"label": label, "why": f'This layer has {dropped} invalid changes that were not saved'})
        if not hunks:
            continue
        at = str(layer.get("at") or "")
        try:


            old = bool(at) and datetime.fromisoformat(at) < cutoff
        except (ValueError, TypeError):
            old = False
        if old:


            evicted.append({
                "label": label, "at": at,
                "why": (f'Settled layer older than {CHANGE_LAYER_MAX_AGE_DAYS} days; removed'
                        if not _layer_is_live({"hunks": hunks})
                        else f'Unsettled layer older than {CHANGE_LAYER_MAX_AGE_DAYS} days; removed'),
            })
            continue
        source = str(layer.get("source") or "other")
        state = str(layer.get("state") or "on")
        cleaned.append({
            "id": str(layer.get("id") or uuid.uuid4().hex[:12]),
            "label": label,
            "source": source if source in CHANGE_LAYER_SOURCES else "other",
            "run_id": str(layer.get("run_id") or ""),
            "round_no": int(layer.get("round_no") or 0),
            "seq": int(layer.get("seq") if isinstance(layer.get("seq"), int) else i),
            "state": state if state in LAYER_STATES else "on",
            "at": at,
            "content_tag": str(layer.get("content_tag") or ""),
            "hunks": hunks,
        })


    drop: set[int] = set()
    live_idx = [i for i, l in enumerate(cleaned) if _layer_is_live(l)]
    done_idx = [i for i, l in enumerate(cleaned) if not _layer_is_live(l)]
    for idxs, cap, why in (
        (live_idx, CHANGE_LAYER_KEEP,
         f'This note has more than {CHANGE_LAYER_KEEP} change layers; oldest layers were dropped'),
        (done_idx, CHANGE_LAYER_SETTLED_KEEP,
         f'This note has more than {CHANGE_LAYER_SETTLED_KEEP} settled change layers; oldest layers were dropped'),
    ):
        if len(idxs) > cap:
            for i in idxs[:len(idxs) - cap]:
                drop.add(i)
                evicted.append({"label": cleaned[i]["label"], "at": cleaned[i]["at"], "why": why})
    if drop:
        cleaned = [l for i, l in enumerate(cleaned) if i not in drop]
    now = _now()
    with connect() as c:

        born = {str(r[0]): str(r[1]) for r in c.execute(
            "SELECT id, created_at FROM note_change_layers WHERE user_id=? AND note_id=?",
            (user_id, note_id))}
        for layer in cleaned:
            _archive_layer_feedback_locked(c, user_id, note_id, layer)
        c.execute("DELETE FROM note_change_layers WHERE user_id=? AND note_id=?", (user_id, note_id))
        for l in cleaned:
            c.execute(
                "INSERT INTO note_change_layers"
                " (id,user_id,note_id,label,source,run_id,round_no,seq,state,at,content_tag,hunks,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (l["id"], user_id, note_id, l["label"], l["source"], l["run_id"], l["round_no"],
                 l["seq"], l["state"], l["at"], l["content_tag"],
                 json.dumps(l["hunks"], ensure_ascii=False), born.get(l["id"], now), now))
        c.commit()
    return {"saved": len(cleaned), "evicted": evicted, "rejected": rejected}


def drop_change_layers(user_id: str, note_id: str) -> int:
    with connect() as c:
        cur = c.execute("DELETE FROM note_change_layers WHERE user_id=? AND note_id=?",
                        (user_id, note_id))
        c.commit()
        return int(cur.rowcount or 0)


class LayersStillPending(RuntimeError):
    pass


def burn_change_layers(user_id: str, note_id: str) -> int:
    with connect() as c:
        rows = c.execute(
            "SELECT * FROM note_change_layers WHERE user_id=? AND note_id=?",
            (user_id, note_id)).fetchall()
        for row in rows:
            layer = dict(row)
            try:
                layer["hunks"] = json.loads(layer.get("hunks") or "[]")
            except (TypeError, ValueError):
                layer["hunks"] = []
            _archive_layer_feedback_locked(c, user_id, note_id, layer, accept_live=True)
        c.commit()
    n = drop_change_layers(user_id, note_id)
    with connect() as c:
        left = int(c.execute(
            "SELECT count(*) FROM note_change_layers WHERE user_id=? AND note_id=?",
            (user_id, note_id)).fetchone()[0])
    if left:
        raise LayersStillPending(
            f'After committing changes, the note still has {left} pending layers that no longer match the body')
    return n


def open_harness_edit(user_id: str, note_id: str, *, run_id: str, key: str,
                      revision_id: str, base_chars: int, ai_chars: int) -> str:
    row_id = uuid.uuid4().hex[:12]
    with connect() as c:
        c.execute("UPDATE harness_edits SET status='superseded', edited_at=?"
                  " WHERE user_id=? AND note_id=? AND status='open'",
                  (_now(), user_id, note_id))
        c.execute(
            "INSERT INTO harness_edits (id,user_id,note_id,run_id,key,revision_id,"
            "status,base_chars,ai_chars,user_chars,kept_chars,created_at,edited_at) "
            "VALUES (?,?,?,?,?,?,'open',?,?,0,0,?,'')",
            (row_id, user_id, note_id, run_id, key, revision_id,
             int(base_chars), int(ai_chars), _now()))
        c.commit()
    return row_id


def _close_harness_edit_locked(c: sqlite3.Connection, user_id: str, note_id: str,
                               content: str) -> None:
    row = c.execute("SELECT id, revision_id FROM harness_edits"
                    " WHERE user_id=? AND note_id=? AND status='open'"
                    " ORDER BY created_at DESC, rowid DESC LIMIT 1",
                    (user_id, note_id)).fetchone()
    if not row:
        return
    rev = c.execute("SELECT content FROM note_revisions WHERE id=? AND user_id=?",
                    (row["revision_id"], user_id)).fetchone()
    if not rev:


        c.execute("UPDATE harness_edits SET status='lost', edited_at=? WHERE id=?",
                  (_now(), row["id"]))
        return
    ai = rev["content"] or ""
    if ai == content:
        return
    c.execute("UPDATE harness_edits SET status='edited', user_chars=?, kept_chars=?,"
              " edited_at=? WHERE id=?",
              (len(content), kept_chars(ai, content), _now(), row["id"]))


def kept_chars(before: str, after: str) -> int:
    import difflib

    sm = difflib.SequenceMatcher(None, before or "", after or "", autojunk=False)
    return sum(b.size for b in sm.get_matching_blocks())


def harness_edits(user_id: str = "", limit: int = 200) -> list[dict]:
    with connect() as c:
        if user_id:
            rows = c.execute("SELECT * FROM harness_edits WHERE user_id=?"
                             " ORDER BY created_at DESC, rowid DESC LIMIT ?",
                             (user_id, limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM harness_edits"
                             " ORDER BY created_at DESC, rowid DESC LIMIT ?",
                             (limit,)).fetchall()
    return [dict(r) for r in rows]


def latest_harness_retention(user_id: str, note_id: str) -> dict | None:
    with connect() as c:
        row = c.execute(
            "SELECT * FROM harness_edits WHERE user_id=? AND note_id=? AND status='edited'"
            " ORDER BY edited_at DESC, rowid DESC LIMIT 1", (user_id, note_id)).fetchone()
        if not row:
            return None
        ai_row = c.execute("SELECT content FROM note_revisions WHERE id=? AND user_id=?",
                           (row["revision_id"], user_id)).fetchone()
        base_row = c.execute(
            "SELECT content FROM note_revisions WHERE user_id=? AND note_id=? AND run_id=?"
            " AND reason='round' ORDER BY round_no, created_at, rowid LIMIT 1",
            (user_id, note_id, row["run_id"])).fetchone()
        user_row = c.execute("SELECT content FROM notes WHERE user_id=? AND id=?",
                             (user_id, note_id)).fetchone()
    if not ai_row or not user_row:
        return None
    import difflib

    base = (base_row["content"] if base_row else "") or ""
    ai = ai_row["content"] or ""
    current = user_row["content"] or ""
    sm = difflib.SequenceMatcher(None, base, ai, autojunk=False)
    additions: list[tuple[str, str]] = []
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag not in ("insert", "replace") or j2 <= j1:
            continue
        text = ai[j1:j2]
        heading = 'Body'
        for line in reversed(ai[:j1].splitlines()):
            if line.lstrip().startswith("#"):
                heading = line.lstrip("# ").strip() or 'Body'
                break


        for part in re.split(r"(?m)(?=^#{1,6}\s+)", text):
            if not part:
                continue
            first = part.lstrip().splitlines()[0] if part.lstrip() else ""
            if first.startswith("#"):
                heading = first.lstrip("# ").strip() or heading
            additions.append((heading, part))
    generated = sum(len(text) for _heading, text in additions)
    if generated <= 0:
        generated = max(0, int(row["ai_chars"]) - int(row["base_chars"]))
    kept = 0
    by_section: dict[str, list[int]] = {}
    for heading, text in additions:
        matched = kept_chars(text, current)
        kept += matched
        stats = by_section.setdefault(heading, [0, 0])
        stats[0] += len(text)
        stats[1] += matched
    kept = min(generated, kept)
    changed = ""
    if by_section:
        changed = max(by_section, key=lambda h: by_section[h][0] - by_section[h][1])
    return {
        "run_id": row["run_id"], "generated_chars": generated, "kept_chars": kept,
        "kept_percent": round(100 * kept / generated) if generated else 0,
        "changed_section": changed, "edited_at": row["edited_at"],
    }


def retention_calibration(user_id: str, *, min_samples: int = 30) -> dict | None:
    with connect() as c:
        rows = c.execute(
            "SELECT e.base_chars,e.ai_chars,e.kept_chars,r.final_scores"
            " FROM harness_edits e JOIN harness_runs r ON r.id=e.run_id"
            " WHERE e.user_id=? AND e.status='edited' ORDER BY e.edited_at DESC LIMIT 300",
            (user_id,)).fetchall()
    if len(rows) < min_samples:
        return None
    by_dim: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        generated = max(1, int(row["ai_chars"]) - int(row["base_chars"]))
        kept = max(0, int(row["kept_chars"]) - int(row["base_chars"]))
        pct = min(100.0, 100.0 * kept / generated)
        try:
            scores = json.loads(row["final_scores"] or "{}")
        except (TypeError, ValueError):
            continue
        for dim, level in scores.items():
            group = "pass" if int(level) >= 2 else "weak"
            by_dim.setdefault(dim, {"pass": [], "weak": []})[group].append(pct)
    signals = []
    for dim, groups in by_dim.items():
        if min(len(groups["pass"]), len(groups["weak"])) < 5:
            continue
        pass_avg = sum(groups["pass"]) / len(groups["pass"])
        weak_avg = sum(groups["weak"]) / len(groups["weak"])
        signals.append({"dimension": dim, "retention_gap": round(pass_avg - weak_avg),
                        "pass_n": len(groups["pass"]), "weak_n": len(groups["weak"])})
    signals.sort(key=lambda x: abs(x["retention_gap"]), reverse=True)
    return {"samples": len(rows), "signals": signals}


def list_revisions(user_id: str, note_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT id, note_id, title, reason, run_id, round_no, created_at, content"

            " FROM note_revisions WHERE user_id=? AND note_id=? ORDER BY created_at DESC, rowid DESC",
            (user_id, note_id)).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        d["chars"] = word_count(d.pop("content") or "")
        out.append(d)
    return out


def get_revision(user_id: str, note_id: str, rev_id: str) -> dict | None:
    with connect() as c:
        row = c.execute(
            "SELECT id, note_id, title, content, reason, run_id, round_no, created_at FROM note_revisions"
            " WHERE user_id=? AND note_id=? AND id=?", (user_id, note_id, rev_id)).fetchone()
    return dict(row) if row else None


def restore_revision(user_id: str, note_id: str, rev_id: str) -> dict | None:
    rev = get_revision(user_id, note_id, rev_id)
    if not rev:
        return None
    snapshot_note(user_id, note_id, "before_restore")
    with connect() as c:
        c.execute("UPDATE notes SET title=?, content=?, updated_at=? WHERE user_id=? AND id=?",
                  (rev["title"], rev["content"], _now(), user_id, note_id))


        _close_harness_edit_locked(c, user_id, note_id, rev["content"] or "")
    sync_citations(user_id, note_id, rev["content"])
    return get_note(user_id, note_id)


#     （`checks/skeleton.BEAT_TARGET_CHARS`）；


SPINE_MAX = 200
BEAT_MAX = 200
_BOUNDARY = "。；;！？!?，,、"


def trim_to_boundary(text: str, limit: int) -> str:
    s = " ".join((text or "").split())
    if len(s) <= limit:
        return s
    head = s[:limit]
    cut = max(head.rfind(ch) for ch in _BOUNDARY)
    if cut >= limit // 2:
        return head[:cut].rstrip("，,、；;") + "。" if head[cut] not in "。！？!?" else head[:cut + 1]
    return head[:limit - 1].rstrip() + "…"


LEGACY_BEAT_MAX = 60
_SENTENCE_END = "。！？；.!?;」”\"'）)"


def truncated_beats(beats: list[str]) -> list[int]:
    return [i for i, b in enumerate(beats or [], 1)
            if isinstance(b, str) and len(b) == LEGACY_BEAT_MAX and b[-1:] not in ("",) and b[-1] not in _SENTENCE_END]


def clamp_skeleton(spine: str, beats: list[str]) -> tuple[str, list[str]]:
    s = trim_to_boundary(spine, SPINE_MAX)
    bs = [trim_to_boundary(str(b), BEAT_MAX) for b in (beats or [])]
    return s, [b for b in bs if b]


def set_skeleton(user_id: str, note_id: str, spine: str, beats: list[str]) -> None:
    spine = " ".join((spine or "").split())
    beats = [" ".join(str(b).split()) for b in (beats or [])]
    beats = [b for b in beats if b]
    if len(spine) > SPINE_MAX:
        raise ValueError(f'The skeleton spine is too long ({len(spine)} characters; limit {SPINE_MAX}）')
    for i, b in enumerate(beats, 1):
        if len(b) > BEAT_MAX:
            raise ValueError(f'Skeleton beat {i} is too long ({len(b)} characters; limit {BEAT_MAX}）')
    with connect() as c:
        c.execute("UPDATE notes SET spine=?, beats=? WHERE user_id=? AND id=?",
                  (spine, json.dumps(beats, ensure_ascii=False), user_id, note_id))


def set_pinned(user_id: str, note_id: str, pinned: bool) -> dict | None:
    with connect() as c:
        cur = c.execute(
            "UPDATE notes SET pinned=? WHERE user_id=? AND id=?",
            (1 if pinned else 0, user_id, note_id))
        if cur.rowcount == 0:
            return None
    return get_note(user_id, note_id)


def set_intent(user_id: str, note_id: str, intent: dict) -> dict | None:
    d = intent_mod.normalize(intent)
    with connect() as c:
        cur = c.execute("UPDATE notes SET intent=? WHERE user_id=? AND id=?",
                        (json.dumps(d, ensure_ascii=False), user_id, note_id))
        if cur.rowcount == 0:
            return None
    return get_note(user_id, note_id)


TRAY_KINDS = ("note", "fact", "import", "selection")
TRAY_MAX_ITEMS = 24
TRAY_EXCERPT_MAX = 600
TRAY_TITLE_MAX = 120
TRAY_REF_MAX = 512


def _tray_row(row) -> dict:
    d = dict(row)
    return {"id": d["id"], "kind": d["kind"], "ref_id": d.get("ref_id") or "", "title": d.get("title") or "",
            "excerpt": d.get("excerpt") or "", "position": int(d.get("position") or 0), "added_at": d.get("added_at") or ""}


def normalize_tray_item(item: dict) -> dict | None:
    kind = str((item or {}).get("kind") or "").strip()
    if kind not in TRAY_KINDS:
        return None

    ref_id = str(item.get("ref_id") or "").strip()[:TRAY_REF_MAX]
    title = str(item.get("title") or "").strip()[:TRAY_TITLE_MAX]
    excerpt = str(item.get("excerpt") or "").strip()[:TRAY_EXCERPT_MAX]
    if kind in ("note", "fact") and not ref_id:
        return None
    if kind in ("import", "selection") and not excerpt:
        return None
    iid = str(item.get("id") or "").strip()[:32] or uuid.uuid4().hex[:12]
    return {"id": iid, "kind": kind, "ref_id": ref_id, "title": title, "excerpt": excerpt}


def list_tray(user_id: str, note_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM note_tray WHERE user_id=? AND note_id=? ORDER BY position, added_at",
                         (user_id, note_id)).fetchall()
    return [_tray_row(r) for r in rows]


def replace_tray(user_id: str, note_id: str, items: list[dict]) -> list[dict]:
    now = _now()
    seen: set[tuple[str, str, str]] = set()
    kept: list[dict] = []
    for raw in items or ():
        d = normalize_tray_item(raw)
        if not d:
            continue
        key = (d["kind"], d["ref_id"], d["excerpt"] if d["kind"] in ("import", "selection") else "")
        if key in seen:
            continue
        seen.add(key)
        kept.append(d)
        if len(kept) >= TRAY_MAX_ITEMS:
            break
    with connect() as c:
        old = {r["id"]: r["added_at"] for r in c.execute(
            "SELECT id, added_at FROM note_tray WHERE user_id=? AND note_id=?", (user_id, note_id))}
        c.execute("DELETE FROM note_tray WHERE user_id=? AND note_id=?", (user_id, note_id))
        for pos, d in enumerate(kept):
            c.execute("INSERT INTO note_tray (id,user_id,note_id,kind,ref_id,title,excerpt,position,added_at) "
                      "VALUES (?,?,?,?,?,?,?,?,?)",
                      (d["id"], user_id, note_id, d["kind"], d["ref_id"], d["title"], d["excerpt"], pos,
                       old.get(d["id"]) or now))
        c.commit()
    return list_tray(user_id, note_id)


def delete_tray_item(user_id: str, note_id: str, item_id: str) -> bool:
    with connect() as c:
        cur = c.execute("DELETE FROM note_tray WHERE user_id=? AND note_id=? AND id=?", (user_id, note_id, item_id))
        c.commit()
    return cur.rowcount > 0


def set_icon(user_id: str, note_id: str, icon: str) -> dict | None:
    with connect() as c:
        cur = c.execute("UPDATE notes SET icon=? WHERE user_id=? AND id=?", (icon, user_id, note_id))
        if cur.rowcount == 0:
            return None
    return get_note(user_id, note_id)


def delete_note(user_id: str, note_id: str) -> list[str]:
    removed: list[str] = []
    with connect() as c:
        if not c.execute("SELECT 1 FROM notes WHERE user_id=? AND id=?",
                         (user_id, note_id)).fetchone():
            return removed

        def drop(nid: str) -> None:
            kids = [r[0] for r in c.execute(
                "SELECT note_id FROM branches WHERE parent_note_id=? AND user_id=?",
                (nid, user_id))]
            for kid in kids:
                others = c.execute(
                    "SELECT COUNT(*) FROM branches WHERE note_id=? AND user_id=?"
                    " AND parent_note_id<>?", (kid, user_id, nid)).fetchone()[0]
                if others:

                    c.execute("DELETE FROM branches WHERE note_id=? AND"
                              " parent_note_id=? AND user_id=?", (kid, nid, user_id))
                else:
                    drop(kid)


            note_row = c.execute("SELECT * FROM notes WHERE id=? AND user_id=?", (nid, user_id)).fetchone()


            if note_row is not None and not (note_row["content"] or "").strip() \
                    and (note_row["title"] or "").strip() in ("", '\u672a\u547d\u540d', "Untitled", "note"):
                note_row = None
            if note_row is not None:
                nd = dict(note_row)
                payload = {
                    "note": nd,
                    "branches": [dict(r) for r in c.execute(
                        "SELECT * FROM branches WHERE note_id=? AND user_id=?", (nid, user_id))],
                    "revisions": [dict(r) for r in c.execute(
                        "SELECT * FROM note_revisions WHERE user_id=? AND note_id=? ORDER BY created_at DESC LIMIT 20",
                        (user_id, nid))],
                }
                c.execute("INSERT OR REPLACE INTO note_trash (user_id,note_id,title,chars,payload,deleted_at) VALUES (?,?,?,?,?,?)",
                          (user_id, nid, nd.get("title") or "", word_count(nd.get("content") or ""),
                           json.dumps(payload, ensure_ascii=False), _now()))
            c.execute("DELETE FROM branches WHERE note_id=? AND user_id=?",
                      (nid, user_id))
            c.execute("DELETE FROM notes WHERE id=? AND user_id=?", (nid, user_id))


            c.execute("DELETE FROM note_citations WHERE user_id=? AND note_id=?", (user_id, nid))
            c.execute("DELETE FROM note_revisions WHERE user_id=? AND note_id=?", (user_id, nid))
            c.execute("DELETE FROM harness_snapshots WHERE user_id=? AND note_id=?", (user_id, nid))

            c.execute("DELETE FROM harness_runs WHERE key=? OR key LIKE ?", (nid, f"%:{nid}"))


            c.execute("DELETE FROM harness_edits WHERE user_id=? AND note_id=?", (user_id, nid))

            c.execute("DELETE FROM note_tray WHERE user_id=? AND note_id=?", (user_id, nid))

            c.execute("DELETE FROM note_change_layers WHERE user_id=? AND note_id=?", (user_id, nid))
            c.execute("DELETE FROM writing_feedback WHERE user_id=? AND note_id=?", (user_id, nid))
            removed.append(nid)

        drop(note_id)


        if removed:
            q = ",".join("?" * len(removed))
            c.execute(f"UPDATE writing_plans SET status='abandoned' WHERE user_id=? AND status='active' AND parent_note_id IN ({q})",
                      [user_id, *removed])
        c.commit()
    return removed
def record_llm_usage(user_id: str, feature: str, model: str, prompt_tokens: int,
                     completion_tokens: int, ms: int, cached_tokens: int = 0,
                     cache_write_tokens: int = 0) -> None:
    with connect() as c:
        c.execute("INSERT INTO llm_usage (user_id,feature,model,prompt_tokens,completion_tokens,"
                  "ms,cached_tokens,cache_write_tokens,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                  (user_id, feature[:60], model[:80], int(prompt_tokens or 0),
                   int(completion_tokens or 0), int(ms or 0),
                   int(cached_tokens or 0), int(cache_write_tokens or 0), _now()))


EXTRACT_PROMPT_FIXED_TOKENS = 1200
EXTRACT_TOKENS_PER_FACT = 60


def record_extract_estimate(user_id: str, chars: int, facts: int, ms: int) -> None:
    try:
        model = get_active_llm_config().get("model", "")
    except Exception:      # noqa: BLE001
        model = ""
    record_llm_usage(user_id, "kb/extract~", model,
                     EXTRACT_PROMPT_FIXED_TOKENS + int(chars / 1.5), EXTRACT_TOKENS_PER_FACT * max(0, int(facts)), ms)


def usage_summary(user_id: str) -> dict:
    now = datetime.now(timezone.utc)
    out: dict = {}
    with connect() as c:
        for key, days in (("today", 1), ("week", 7), ("month", 30), ("all", None)):
            if days is None:
                row = c.execute("SELECT COUNT(*), COALESCE(SUM(prompt_tokens),0), COALESCE(SUM(completion_tokens),0), COALESCE(SUM(ms),0)"
                                " FROM llm_usage WHERE user_id=?", (user_id,)).fetchone()
            else:
                since = (now - timedelta(days=days)).isoformat(timespec="seconds")
                row = c.execute("SELECT COUNT(*), COALESCE(SUM(prompt_tokens),0), COALESCE(SUM(completion_tokens),0), COALESCE(SUM(ms),0)"
                                " FROM llm_usage WHERE user_id=? AND created_at>=?", (user_id, since)).fetchone()
            out[key] = {"calls": row[0], "prompt_tokens": row[1], "completion_tokens": row[2], "ms": row[3]}
        since = (now - timedelta(days=30)).isoformat(timespec="seconds")
        rows = c.execute("SELECT feature, COUNT(*), COALESCE(SUM(prompt_tokens+completion_tokens),0)"
                         " FROM llm_usage WHERE user_id=? AND created_at>=? GROUP BY feature ORDER BY 3 DESC LIMIT 8",
                         (user_id, since)).fetchall()
        out["by_feature"] = [{"feature": r[0], "calls": r[1], "tokens": r[2]} for r in rows]
        out["models"] = [r[0] for r in c.execute("SELECT DISTINCT model FROM llm_usage WHERE user_id=? AND created_at>=?", (user_id, since)).fetchall()]
    return out


TRASH_KEEP_DAYS = 30


def prune_trash(user_id: str, days: int = TRASH_KEEP_DAYS) -> int:
    cutoff = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days)).isoformat(timespec="seconds")
    with connect() as c:
        return c.execute("DELETE FROM note_trash WHERE user_id=? AND deleted_at < ?", (user_id, cutoff)).rowcount


def list_trash(user_id: str) -> list[dict]:
    prune_trash(user_id)
    with connect() as c:
        rows = c.execute("SELECT note_id, title, chars, deleted_at FROM note_trash WHERE user_id=? ORDER BY deleted_at DESC",
                         (user_id,)).fetchall()
    return [dict(r) for r in rows]


def restore_from_trash(user_id: str, note_id: str) -> dict | None:
    with connect() as c:
        if not _restore_one(c, user_id, note_id, set()):
            return None
        c.commit()
    return get_note(user_id, note_id)


def _restore_one(c, user_id: str, note_id: str, seen: set[str]) -> bool:
    if note_id in seen:
        return False
    seen.add(note_id)
    row = c.execute("SELECT payload FROM note_trash WHERE user_id=? AND note_id=?", (user_id, note_id)).fetchone()
    if row is None:
        return False
    payload = json.loads(row["payload"])
    nd = payload["note"]
    if c.execute("SELECT 1 FROM notes WHERE id=?", (note_id,)).fetchone():
        c.execute("DELETE FROM note_trash WHERE user_id=? AND note_id=?", (user_id, note_id))
        return True
    cols = [k for k in nd.keys()]
    c.execute(f"INSERT INTO notes ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", [nd[k] for k in cols])
    branches = payload.get("branches") or []
    if not branches:
        branches = [{"note_id": note_id, "parent_note_id": ROOT_ID, "user_id": user_id}]
    for b in branches:
        parent = b.get("parent_note_id") or ROOT_ID
        if parent != ROOT_ID and not c.execute("SELECT 1 FROM notes WHERE id=?", (parent,)).fetchone():

            if not _restore_one(c, user_id, parent, seen):
                parent = ROOT_ID
        if c.execute("SELECT 1 FROM branches WHERE note_id=? AND parent_note_id=?", (note_id, parent)).fetchone():
            continue
        bcols = [k for k in b.keys() if k != "parent_note_id"]
        vals = [b[k] for k in bcols]
        c.execute(f"INSERT INTO branches ({','.join(bcols)},parent_note_id) VALUES ({','.join('?' * len(bcols))},?)", [*vals, parent])
    for r in payload.get("revisions") or []:
        rcols = list(r.keys())
        c.execute(f"INSERT OR IGNORE INTO note_revisions ({','.join(rcols)}) VALUES ({','.join('?' * len(rcols))})", [r[k] for k in rcols])
    c.execute("DELETE FROM note_trash WHERE user_id=? AND note_id=?", (user_id, note_id))
    return True


def purge_trash(user_id: str, note_id: str) -> bool:
    with connect() as c:
        return c.execute("DELETE FROM note_trash WHERE user_id=? AND note_id=?", (user_id, note_id)).rowcount > 0


_WEEKDAYS = "Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split()
_LEGACY_WEEKDAYS = '\u5468\u4e00 \u5468\u4e8c \u5468\u4e09 \u5468\u56db \u5468\u4e94 \u5468\u516d \u5468\u65e5'.split()


def _child_titled(c, user_id: str, parent_id: str, title: str) -> str | None:
    row = c.execute("SELECT n.id FROM notes n JOIN branches b ON b.note_id=n.id"
                    " WHERE b.user_id=? AND b.parent_note_id=? AND n.title=? ORDER BY b.position LIMIT 1",
                    (user_id, parent_id, title)).fetchone()
    return row[0] if row else None


def journal_node(user_id: str, day, depth: int = 4) -> str:
    chain = [("Journal", "", "bx-calendar"), (str(day.year), "", "bx-folder"),
             (f"{day.month:02d}", "", "bx-folder"),
             (f"{day.month:02d}-{day.day:02d} {_WEEKDAYS[day.weekday()]}",
              f"# {day.isoformat()} {_WEEKDAYS[day.weekday()]}\n\n", "bx-calendar-event")]
    legacy_titles = ['\u65e5\u8bb0', str(day.year), f'{day.month:02d} \u6708',
                     f"{day.month:02d}-{day.day:02d} {_LEGACY_WEEKDAYS[day.weekday()]}"]
    parent = ROOT_ID
    note_id = ROOT_ID
    for index, (title, content, icon) in enumerate(chain[:max(1, depth)]):
        with connect() as c:
            note_id = (_child_titled(c, user_id, parent, title)
                       or _child_titled(c, user_id, parent, legacy_titles[index]))
        if note_id is None:
            note_id = create_note(user_id, title, content, parent)["id"]
            set_icon(user_id, note_id, icon)
        parent = note_id
    return note_id


def today_note(user_id: str, today) -> dict:
    return get_note(user_id, journal_node(user_id, today, depth=4))


def upsert_child(user_id: str, parent_id: str, title: str, content: str,
                 *, source: str = "", icon: str = "") -> dict:
    with connect() as c:
        nid = _child_titled(c, user_id, parent_id, title)
    if nid:

        update_note(user_id, nid, title=title, content=content, source="harness")
        return get_note(user_id, nid)
    note = create_note(user_id, title, content, parent_id, source=source)
    if icon:
        set_icon(user_id, note["id"], icon)
    return get_note(user_id, note["id"])


DERIVED_SOURCES = ("slides", "journey")


def child_notes(user_id: str, parent_id: str, exclude_id: str = "",
                limit: int = 5) -> list[dict]:
    holes = ",".join("?" * len(DERIVED_SOURCES))
    with connect() as c:
        rows = c.execute(
            "SELECT n.* FROM notes n JOIN branches b ON b.note_id = n.id"
            f" WHERE b.user_id=? AND b.parent_note_id=? AND n.id != ?"
            f" AND COALESCE(n.source,'') NOT IN ({holes})"
            " ORDER BY n.updated_at DESC LIMIT ?",
            (user_id, parent_id, exclude_id, *DERIVED_SOURCES, limit)).fetchall()
    return [_note(r) for r in rows]


import re as _re


_CITE = _re.compile(r"\[((?:[A-Za-z][A-Za-z0-9_-]*-(?:\d+|[0-9a-f]{12})-[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9_-]*-manualF[1-9]\d*))\]")


def cited_fact_ids(content: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in _CITE.finditer(content or ""):
        seen.setdefault(m.group(1), None)
    return list(seen)


def sync_citations(user_id: str, note_id: str, content: str) -> list[str]:
    ids = cited_fact_ids(content)
    with connect() as c:
        c.execute("DELETE FROM note_citations WHERE note_id=? AND user_id=?",
                  (note_id, user_id))
        c.executemany(
            "INSERT OR IGNORE INTO note_citations (note_id, fact_id, user_id)"
            " VALUES (?,?,?)", [(note_id, f, user_id) for f in ids])
        c.commit()
    return ids


def reindex_citations() -> int:
    fixed = 0
    with connect() as c:
        rows = c.execute("SELECT id, user_id, content FROM notes").fetchall()
        for r in rows:
            want = set(cited_fact_ids(r["content"] or ""))
            have = {x["fact_id"] for x in c.execute("SELECT fact_id FROM note_citations WHERE note_id=? AND user_id=?", (r["id"], r["user_id"]))}
            if want != have:
                c.execute("DELETE FROM note_citations WHERE note_id=? AND user_id=?", (r["id"], r["user_id"]))
                c.executemany("INSERT OR IGNORE INTO note_citations (note_id, fact_id, user_id) VALUES (?,?,?)",
                              [(r["id"], f, r["user_id"]) for f in want])
                fixed += 1
        c.commit()
    return fixed


def notes_citing(user_id: str, fact_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT n.id, n.title, n.updated_at, n.icon, substr(n.content,1,80) AS preview FROM note_citations k"
            " JOIN notes n ON n.id = k.note_id"
            " WHERE k.user_id=? AND k.fact_id=? ORDER BY n.updated_at DESC",
            (user_id, fact_id)).fetchall()
    return [dict(r) for r in rows]


_NOTE_LINK = _re.compile(r"\]\(note://([0-9a-f]{12})\)")


def note_links_in(content: str) -> list[str]:
    seen: list[str] = []
    for m in _NOTE_LINK.finditer(content or ""):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def backlinks(user_id: str, note_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT id, title, updated_at, icon, substr(content,1,80) AS preview FROM notes"
            " WHERE user_id=? AND id<>? AND content LIKE ? ORDER BY updated_at DESC",
            (user_id, note_id, f"%](note://{note_id})%")).fetchall()
    return [dict(r) for r in rows]


def mark_ingested(user_id: str, note_id: str) -> None:
    with connect() as c:
        c.execute("UPDATE notes SET ingested_at=? WHERE id=? AND user_id=?",
                  (_now(), note_id, user_id))
        c.commit()


def _next_position(c: sqlite3.Connection, user_id: str, parent_id: str) -> int:
    row = c.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM branches"
                    " WHERE user_id=? AND parent_note_id=?",
                    (user_id, parent_id)).fetchone()
    return int(row[0])


def attach(user_id: str, note_id: str, parent_id: str = ROOT_ID,
           position: int | None = None) -> dict:
    with connect() as c:

        if note_id == parent_id or _would_cycle(c, note_id, parent_id):
            raise ValueError('Cannot move a note into its own subtree')
        row = c.execute("SELECT * FROM branches WHERE note_id=? AND parent_note_id=?",
                        (note_id, parent_id)).fetchone()
        if row:
            return dict(row)
        bid = uuid.uuid4().hex[:12]
        pos = _next_position(c, user_id, parent_id) if position is None else position
        c.execute("INSERT INTO branches (id, user_id, note_id, parent_note_id,"
                  " position, is_expanded, created_at) VALUES (?,?,?,?,?,0,?)",
                  (bid, user_id, note_id, parent_id, pos, _now()))
        c.commit()
        return dict(c.execute("SELECT * FROM branches WHERE id=?", (bid,)).fetchone())


def detach(user_id: str, note_id: str, parent_id: str) -> bool:
    with connect() as c:
        n = c.execute("SELECT COUNT(*) FROM branches WHERE note_id=? AND user_id=?",
                      (note_id, user_id)).fetchone()[0]
        if n <= 1:
            return False
        cur = c.execute("DELETE FROM branches WHERE note_id=? AND parent_note_id=?"
                        " AND user_id=?", (note_id, parent_id, user_id))
        c.commit()
        return cur.rowcount > 0


def _would_cycle(c: sqlite3.Connection, note_id: str, new_parent: str) -> bool:
    seen = {new_parent}
    frontier = [new_parent]
    while frontier:
        cur = frontier.pop()
        if cur == note_id:
            return True
        for row in c.execute("SELECT parent_note_id FROM branches WHERE note_id=?",
                             (cur,)):
            if row[0] not in seen:
                seen.add(row[0])
                frontier.append(row[0])
    return False


def move_branch(user_id: str, note_id: str, old_parent: str, new_parent: str,
                position: int | None = None) -> bool:
    with connect() as c:
        if note_id == new_parent or _would_cycle(c, note_id, new_parent):
            return False
        if c.execute("SELECT 1 FROM branches WHERE note_id=? AND parent_note_id=?"
                     " AND user_id=?", (note_id, new_parent, user_id)).fetchone():

            return detach(user_id, note_id, old_parent)
        pos = _next_position(c, user_id, new_parent) if position is None else position
        cur = c.execute("UPDATE branches SET parent_note_id=?, position=?"
                        " WHERE note_id=? AND parent_note_id=? AND user_id=?",
                        (new_parent, pos, note_id, old_parent, user_id))
        c.commit()
        return cur.rowcount > 0


def reorder(user_id: str, parent_id: str, order: list[str]) -> int:
    with connect() as c:
        rows = c.execute("SELECT note_id FROM branches WHERE parent_note_id=? AND user_id=?"
                         " ORDER BY position", (parent_id, user_id)).fetchall()
        existing = [r["note_id"] for r in rows]
        seen = set()
        final = [n for n in order if n in existing and not (n in seen or seen.add(n))]
        final += [n for n in existing if n not in seen]
        for i, nid in enumerate(final):
            c.execute("UPDATE branches SET position=? WHERE note_id=? AND parent_note_id=?"
                      " AND user_id=?", (i, nid, parent_id, user_id))
        c.commit()
        return len(final)


def set_expanded(user_id: str, note_id: str, parent_id: str, expanded: bool) -> None:
    with connect() as c:
        c.execute("UPDATE branches SET is_expanded=? WHERE note_id=? AND"
                  " parent_note_id=? AND user_id=?",
                  (1 if expanded else 0, note_id, parent_id, user_id))
        c.commit()


def tree(user_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT b.id, b.note_id, b.parent_note_id, b.position, b.is_expanded,       n.title, n.pinned, n.icon, n.updated_at,       n.source,       CASE WHEN n.title IN ('', '\u672a\u547d\u540d', 'Untitled', 'note') THEN substr(n.content, 1, 80) ELSE '' END AS preview,       n.ingested_at,       (SELECT COUNT(*) FROM note_citations k          WHERE k.note_id = b.note_id) AS cite_count,       (SELECT COUNT(*) FROM branches k WHERE k.parent_note_id=b.note_id)         AS child_count,       (SELECT COUNT(*) FROM branches m WHERE m.note_id=b.note_id)         AS branch_count FROM branches b JOIN notes n ON n.id = b.note_id WHERE b.user_id=? ORDER BY b.parent_note_id, b.position, n.title",
            (user_id,)).fetchall()
    return [dict(r) for r in rows]


def note_paths(user_id: str, note_id: str) -> list[list[str]]:
    out: list[list[str]] = []
    with connect() as c:
        def walk(nid: str, below: list[str]) -> None:
            if len(below) > 64:
                return
            trail = [nid] + below
            parents = [r[0] for r in c.execute(
                "SELECT parent_note_id FROM branches WHERE note_id=? AND user_id=?",
                (nid, user_id))]
            if not parents:
                return
            for parent in parents:
                if parent == ROOT_ID:
                    out.append(trail)
                else:
                    walk(parent, trail)

        walk(note_id, [])
    return out


def get_active_plan(user_id: str, parent_note_id: str) -> dict | None:
    with connect() as c:
        row = c.execute(
            "SELECT * FROM writing_plans WHERE user_id=? AND parent_note_id=? AND status='active'",
            (user_id, parent_note_id)).fetchone()
    return dict(row) if row else None


def get_plan(user_id: str, plan_id: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM writing_plans WHERE user_id=? AND id=?",
                        (user_id, plan_id)).fetchone()
    return dict(row) if row else None


def create_plan(user_id: str, parent_note_id: str, goal: str) -> dict:
    plan = {"id": uuid.uuid4().hex[:12], "user_id": user_id, "parent_note_id": parent_note_id,
            "goal": goal, "status": "active", "doc_note_id": "",
            "created_at": _now(), "updated_at": _now()}
    with connect() as c:
        c.execute(
            "UPDATE writing_plans SET status='abandoned' WHERE user_id=? AND parent_note_id=? AND status='active'",
            (user_id, parent_note_id))
        c.execute(
            "INSERT INTO writing_plans (id,user_id,parent_note_id,goal,status,doc_note_id,created_at,updated_at) "
            "VALUES (:id,:user_id,:parent_note_id,:goal,:status,:doc_note_id,:created_at,:updated_at)", plan)
    return plan


def set_plan_doc_note(user_id: str, plan_id: str, note_id: str) -> None:
    with connect() as c:
        c.execute("UPDATE writing_plans SET doc_note_id=? WHERE user_id=? AND id=?",
                  (note_id, user_id, plan_id))


def set_plan_status(user_id: str, plan_id: str, status: str) -> None:
    with connect() as c:
        c.execute("UPDATE writing_plans SET status=?, updated_at=? WHERE user_id=? AND id=?",
                  (status, _now(), user_id, plan_id))


def list_sections(plan_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM writing_sections WHERE plan_id=? ORDER BY idx",
                         (plan_id,)).fetchall()
    return [_note(r) for r in rows]


MAX_PLAN_SECTIONS = 40
MAX_SECTIONS_PER_ADD = 20

SECTION_TITLE_MAX = 80


_TITLE_CITE = re.compile(r"\s*\[(?:[A-Za-z][A-Za-z0-9_-]*-(?:\d+|[0-9a-f]{12})-[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9_-]*-manualF[1-9]\d*)\]")


def _clean_section_title(t: str) -> str:
    return " ".join(_TITLE_CITE.sub("", t or "").split())[:SECTION_TITLE_MAX]


def _section_key(t: str) -> str:
    return " ".join((t or "").split()).lower()


def add_sections(plan_id: str, titles: list[str]) -> list[dict]:
    with connect() as c:
        existing = c.execute("SELECT COALESCE(MAX(idx), -1) FROM writing_sections WHERE plan_id=?",
                             (plan_id,)).fetchone()[0]
        have = {_section_key(r[0]) for r in
                c.execute("SELECT title FROM writing_sections WHERE plan_id=?", (plan_id,)).fetchall()}
        cap = min(MAX_SECTIONS_PER_ADD, max(0, MAX_PLAN_SECTIONS - len(have)))
        picked: list[str] = []
        for t in titles:
            if len(picked) >= cap:
                break
            t = _clean_section_title(t)
            k = _section_key(t)
            if not t or k in have:
                continue
            have.add(k)
            picked.append(t)
        titles = picked
        rows = []
        for offset, title in enumerate(titles):
            row = {"id": uuid.uuid4().hex[:12], "plan_id": plan_id, "idx": existing + 1 + offset,
                   "title": title, "status": "pending", "note_id": "", "summary": "",
                   "created_at": _now()}
            c.execute(
                "INSERT INTO writing_sections (id,plan_id,idx,title,status,note_id,summary,created_at) "
                "VALUES (:id,:plan_id,:idx,:title,:status,:note_id,:summary,:created_at)", row)
            rows.append(row)
    return rows


_SECTION_UPDATABLE_COLS = {"status", "note_id", "summary"}


def update_section(plan_id: str, section_id: str, **fields) -> None:
    if not fields:
        return
    bad = set(fields) - _SECTION_UPDATABLE_COLS
    if bad:
        raise ValueError(f"update_section got unknown column(s): {bad}")
    cols = ", ".join(f"{k}=?" for k in fields)
    with connect() as c:
        c.execute(f"UPDATE writing_sections SET {cols} WHERE plan_id=? AND id=?",
                  (*fields.values(), plan_id, section_id))


def create_job(user_id: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with connect() as c:
        c.execute("INSERT INTO ingest_jobs (id,user_id,status,facts,detail,created_at) "
                  "VALUES (?,?,?,?,?,?)",
                  (job_id, user_id, "queued", 0, "", _now()))
    return job_id


def set_job(job_id: str, status: str, facts: int = 0, detail: str = "") -> None:
    with connect() as c:
        c.execute("UPDATE ingest_jobs SET status=?, facts=?, detail=? WHERE id=?",
                  (status, facts, detail[:500], job_id))


def get_job(job_id: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM ingest_jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(user_id: str, limit: int = 20) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT * FROM ingest_jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)).fetchall()
    return [_note(r) for r in rows]


def request_cancel(job_id: str) -> None:
    with connect() as c:
        c.execute("UPDATE ingest_jobs SET cancel_requested=1 WHERE id=?", (job_id,))


def is_cancel_requested(job_id: str) -> bool:
    job = get_job(job_id)
    return bool(job and job["cancel_requested"])


_SECRETISH = ("sk-proj-", "sk-ant-", "sk-", "ghp_", "gho_", "github_pat_", "xoxb-", "xoxp-")
SECRET_FILENAME = '(credentials redacted)'


def scrub_secret(name: str) -> str:
    s = (name or "").strip()
    if len(s) >= 24 and any(s.startswith(p) for p in _SECRETISH):
        return SECRET_FILENAME
    return name

def create_batch_job(user_id: str, files: list[dict]) -> tuple[str, list[dict]]:
    job_id = uuid.uuid4().hex[:12]
    items: list[dict] = []
    with connect() as c:
        c.execute("INSERT INTO ingest_jobs (id,user_id,status,facts,detail,created_at) "
                  "VALUES (?,?,?,?,?,?)",
                  (job_id, user_id, "queued", 0, "", _now()))
        for idx, f in enumerate(files):
            item = {"id": uuid.uuid4().hex[:12], "job_id": job_id, "idx": idx,
                    "filename": scrub_secret(f["filename"]), "kind": f["kind"], "status": "queued",
                    "facts": 0, "detail": "", "updated_at": _now()}
            c.execute(
                "INSERT INTO ingest_items (id,job_id,idx,filename,kind,status,facts,detail,updated_at) VALUES "
                "(:id,:job_id,:idx,:filename,:kind,:status,:facts,:detail,:updated_at)",
                item)
            items.append(item)
    return job_id, items


def set_item(item_id: str, status: str, facts: int = 0, detail: str = "",
             chunks_total: int | None = None, chunks_done: int | None = None,
             note_id: str | None = None) -> None:
    with connect() as c:
        c.execute(
            "UPDATE ingest_items SET status=?, facts=?, detail=?, updated_at=? WHERE id=?",
            (status, facts, detail[:500], _now(), item_id))
        if chunks_total is not None:
            c.execute("UPDATE ingest_items SET chunks_total=? WHERE id=?", (chunks_total, item_id))
        if chunks_done is not None:
            c.execute("UPDATE ingest_items SET chunks_done=? WHERE id=?", (chunks_done, item_id))
        if note_id is not None:
            c.execute("UPDATE ingest_items SET note_id=? WHERE id=?", (str(note_id)[:32], item_id))


DEFAULT_CHUNK_MS = 13000
TOKENS_PER_CHUNK_FIXED = 1600


def bump_job_chunk(job_id: str, ms: int, chars: int) -> None:
    with connect() as c:
        c.execute("UPDATE ingest_jobs SET chunk_ms=chunk_ms+?, chars_done=chars_done+?, chunks_done=chunks_done+?"
                  " WHERE id=?", (int(ms), int(chars), 1, job_id))


def set_job_chunks_total(job_id: str, n: int) -> None:
    with connect() as c:
        c.execute("UPDATE ingest_jobs SET chunks_total=? WHERE id=?", (int(n), job_id))


def mark_job_started(job_id: str) -> None:
    with connect() as c:
        c.execute("UPDATE ingest_jobs SET started_at=? WHERE id=? AND started_at=''", (_now(), job_id))


def set_job_payload(job_id: str, path: str) -> None:
    with connect() as c:
        c.execute("UPDATE ingest_jobs SET payload_path=? WHERE id=?", (path, job_id))


def avg_chunk_ms(user_id: str) -> int:
    with connect() as c:
        row = c.execute(
            "SELECT SUM(chunk_ms) AS ms, SUM(chunks_done) AS n FROM ("
            "  SELECT chunk_ms, chunks_done FROM ingest_jobs WHERE user_id=? AND chunks_done>0"
            "  ORDER BY created_at DESC LIMIT 5)", (user_id,)).fetchone()
    if row and row["n"]:
        return max(1000, int(row["ms"] / row["n"]))
    return DEFAULT_CHUNK_MS


def estimate(chunks: int, chars: int, chunk_ms: int = DEFAULT_CHUNK_MS) -> dict:
    return {"chunks": chunks, "seconds": int(chunks * chunk_ms / 1000),
            "tokens": int(chunks * TOKENS_PER_CHUNK_FIXED + chars / 1.5)}


def job_progress(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        return {}
    items = get_items(job_id)
    total = sum(int(i.get("chunks_total") or 0) for i in items) or int(job.get("chunks_total") or 0)
    n = int(job.get("chunks_done") or 0)
    done = sum(int(i.get("chunks_done") or 0) for i in items) if items else n
    per = int(job["chunk_ms"] / n) if n and job.get("chunk_ms") else avg_chunk_ms(job["user_id"])
    remaining = max(0, total - done)
    elapsed = 0
    if job.get("started_at"):
        try:
            elapsed = int((datetime.now(timezone.utc) - datetime.fromisoformat(job["started_at"])).total_seconds())
        except ValueError:
            elapsed = 0
    est = estimate(remaining, 0, per)
    return {
        "chunks_total": total, "chunks_done": done, "eta_s": est["seconds"] if job["status"] in ("queued", "running") else 0,
        "elapsed_s": elapsed,
        "tokens_est": int(n * TOKENS_PER_CHUNK_FIXED + int(job.get("chars_done") or 0) / 1.5),
        "resumable": bool(job.get("payload_path")) and job["status"] == "interrupted",
        "current": next((i["filename"] for i in items if i["status"] not in _TERMINAL_ITEM_STATUSES and i["status"] != "queued"), ""),
    }


def get_items(job_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT * FROM ingest_items WHERE job_id=? ORDER BY idx", (job_id,)).fetchall()
    return [_note(r) for r in rows]


def update_job_from_items(job_id: str) -> None:
    items = get_items(job_id)
    if not items:
        return
    total_facts = sum(i["facts"] for i in items)
    if any(i["status"] == "failed" for i in items):
        status = "error"
    elif all(i["status"] in _TERMINAL_ITEM_STATUSES for i in items):
        status = "cancelled" if all(i["status"] == "cancelled" for i in items) else "done"
    else:


        job = get_job(job_id)
        status = "cancelling" if (job and job["cancel_requested"]) else "running"
    detail = "; ".join(f"{i['filename']}: {i['detail']}" for i in items if i["detail"])
    set_job(job_id, status, facts=total_facts, detail=detail)


def list_profile(user_id: str) -> list[dict]:
    with connect() as c:
        # created_at has 1-second resolution (_now()), and preferences are
        # plausibly added back-to-back within the same second -- rowid (SQLite's
        # implicit, monotonically-increasing insertion order) breaks the tie so
        # "newest first" still holds even when the timestamps are identical.
        rows = c.execute(
            "SELECT * FROM user_profile WHERE user_id=? ORDER BY created_at DESC, rowid DESC",
            (user_id,)).fetchall()
    return [_note(r) for r in rows]


def add_profile_entry(user_id: str, text: str) -> dict:
    entry = {"id": uuid.uuid4().hex[:12], "user_id": user_id, "text": text, "created_at": _now()}
    with connect() as c:
        c.execute("INSERT INTO user_profile VALUES (:id,:user_id,:text,:created_at)", entry)
    return entry


def delete_profile_entry(user_id: str, entry_id: str) -> bool:
    with connect() as c:
        cur = c.execute("DELETE FROM user_profile WHERE user_id=? AND id=?",
                        (user_id, entry_id))
    return cur.rowcount > 0


# ---------------------------------------------------------------- LLM provider config
# Global, not per user — the choice is "which LLM backend this deployment uses", not a personal preference.

_PROVIDER_CONFIG_ID = "default"
_PROVIDER_CONFIG_DEFAULTS = {
    "provider": "local", "gpt_api_key": "", "gpt_model": "gpt-4.1-mini",
    "gpt_base_url": "https://api.openai.com/v1", "asr_base_url": "", "auto_sync_notes": 0,
    "local_base_url": "", "local_model": "", "local_api_key": "",
    "vision_base_url": "", "vision_model": "", "vision_api_key": "",
    "asr_provider": "", "assemblyai_api_key": "", "assemblyai_region": "",
    "speechmatics_api_key": "", "speechmatics_region": "",
}
# All of these mean "omitted = keep the saved value; empty string = clear, fall back to the default"
_PROVIDER_OPTIONAL = ("local_base_url", "local_model", "local_api_key",
                      "vision_base_url", "vision_model", "vision_api_key",
                      "asr_provider", "assemblyai_api_key", "assemblyai_region",
                      "speechmatics_api_key", "speechmatics_region")


def get_provider_config() -> dict:
    """Never set = these defaults (provider='local', then get_active_llm_config() falls back to the .env
    config) — that does not mean the GPT fields are in effect; they are only used when provider really is
    'gpt'."""
    with connect() as c:
        row = c.execute(
            "SELECT * FROM provider_config WHERE id=?", (_PROVIDER_CONFIG_ID,)).fetchone()
    if not row:
        return dict(_PROVIDER_CONFIG_DEFAULTS)
    return {k: row[k] for k in _PROVIDER_CONFIG_DEFAULTS}


def get_provider_credentials(provider: str, cfg: dict | None = None) -> dict:
    """The `{api_key, model, base_url}` saved for one provider (each may be '' = not set).

    The two legacy entries read the old `provider_config` columns (`gpt_*` / `local_*`); every other entry
    reads `provider_credentials`. Each table owns half, **no entry ever has a copy in both**, so there is no
    "which copy wins" question."""
    from ..util.config import PROVIDERS
    if provider not in PROVIDERS:
        return {"api_key": "", "model": "", "base_url": ""}
    if provider in ("gpt", "local"):
        cfg = cfg or get_provider_config()
        return {"api_key": cfg[f"{provider}_api_key"], "model": cfg[f"{provider}_model"],
                "base_url": cfg[f"{provider}_base_url"]}
    with connect() as c:
        row = c.execute("SELECT api_key, model, base_url FROM provider_credentials WHERE provider=?",
                        (provider,)).fetchone()
    if not row:
        return {"api_key": "", "model": "", "base_url": ""}
    return {"api_key": row["api_key"], "model": row["model"], "base_url": row["base_url"]}


def set_provider_credentials(provider: str, *, api_key: str | None = None,
                             model: str | None = None, base_url: str | None = None) -> dict:
    """Write one (non gpt / local) provider's credentials. All three fields: None = keep; '' = clear."""
    from ..util.config import PROVIDERS
    if provider not in PROVIDERS or provider in ("gpt", "local"):
        raise ValueError(f"set_provider_credentials: {provider!r} does not live in this table")
    cur = get_provider_credentials(provider)
    merged = {
        "api_key": cur["api_key"] if api_key is None else api_key.strip(),
        "model": cur["model"] if model is None else model.strip(),
        "base_url": cur["base_url"] if base_url is None else base_url.strip().rstrip("/"),
    }
    with connect() as c:
        c.execute(
            "INSERT INTO provider_credentials (provider, api_key, model, base_url, updated_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(provider) DO UPDATE SET api_key=excluded.api_key, model=excluded.model,"
            " base_url=excluded.base_url, updated_at=excluded.updated_at",
            (provider, merged["api_key"], merged["model"], merged["base_url"], _now()))
    return merged


def set_provider_config(provider: str, gpt_api_key: str | None = None,
                        gpt_model: str | None = None, gpt_base_url: str | None = None,
                        asr_base_url: str | None = None, auto_sync_notes: bool | None = None,
                        *, api_key: str | None = None, model: str | None = None,
                        base_url: str | None = None, **more: str | None) -> dict:
    """Update the global provider config. `provider` is any id in `util/providers.PROVIDERS`.

    gpt_api_key / gpt_model / gpt_base_url passed as None (omitted) keep their saved values, so switching
    'gpt' -> 'local' -> 'gpt' does not require retyping an already saved key.

    `api_key` / `model` / `base_url` (the new-style fields) belong to **the `provider` entry itself**: for 'gpt'
    they land in the `gpt_*` columns, for 'local' in `local_*`, for every other entry in `provider_credentials`.
    Same semantics: None = keep; `api_key` '' = clear; `base_url` '' = preset default (for `gpt` that is the
    official OpenAI address)."""
    from ..util.config import PROVIDERS
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; one of {sorted(PROVIDERS)}")
    if provider == "gpt":
        if api_key is not None:
            gpt_api_key = api_key.strip()
        if model is not None:
            gpt_model = model.strip()
        if base_url is not None:
            gpt_base_url = base_url.strip().rstrip("/") or PROVIDERS["gpt"].base_url
    elif provider == "local":
        if api_key is not None:
            more["local_api_key"] = api_key
        if model is not None:
            more["local_model"] = model
        if base_url is not None:
            more["local_base_url"] = base_url
    elif api_key is not None or model is not None or base_url is not None:
        set_provider_credentials(provider, api_key=api_key, model=model, base_url=base_url)
    current = get_provider_config()
    merged = {
        "provider": provider,
        "gpt_api_key": current["gpt_api_key"] if gpt_api_key is None else gpt_api_key,
        "gpt_model": current["gpt_model"] if gpt_model is None else (gpt_model or current["gpt_model"]),
        "gpt_base_url": current["gpt_base_url"] if gpt_base_url is None else (gpt_base_url or current["gpt_base_url"]),
        # The voice address works like the key: omitted = keep; empty string = clear, fall back to the .env default
        "asr_base_url": current["asr_base_url"] if asr_base_url is None else asr_base_url.strip().rstrip("/"),
        "auto_sync_notes": int(current["auto_sync_notes"]) if auto_sync_notes is None else int(bool(auto_sync_notes)),
    }
    unknown = set(more) - set(_PROVIDER_OPTIONAL)
    if unknown:
        raise TypeError(f"set_provider_config: unknown fields {sorted(unknown)}")
    for k in _PROVIDER_OPTIONAL:
        v = more.get(k)
        merged[k] = current[k] if v is None else (v.strip().rstrip("/") if k.endswith("_url") else v.strip())
    cols = ["id", "updated_at", *merged]
    with connect() as c:
        c.execute(
            f"INSERT OR REPLACE INTO provider_config ({', '.join(cols)}) VALUES ({', '.join(':' + k for k in cols)})",
            {"id": _PROVIDER_CONFIG_ID, "updated_at": _now(), **merged})
    return merged


def get_active_llm_config() -> dict:
    """The LLM endpoint actually in effect — the selected preset's base_url/api_key/model when it has what
    it needs (a key, if it requires one), otherwise the "local model" entry / the .env defaults.

    llm.py and kite_memory.py both read from here, never Settings' llm_* fields directly: Settings uses
    pydantic-settings + @lru_cache and is fixed from env once at process start; changing the settings page
    does not take effect there, and it should not be made mutable at runtime for that — it is for
    "switching deployment environments", a different thing from "the user switching providers in
    settings": the former means editing .env and restarting, the latter reads this table.

    The dict carries `provider` (preset id) and `family` (request-body shape, see `util/providers.py`):
    `llm._payload` / `vision.ask_image` pick the token-limit field by `family`."""
    from ..util.config import PROVIDERS
    cfg = get_provider_config()
    pid = cfg["provider"]
    preset = PROVIDERS.get(pid)
    if preset is not None and pid != "local":
        creds = get_provider_credentials(pid, cfg)
        # a key-requiring entry without a key (e.g. just switched, form not saved yet) falls back to the
        # local model: safer than sending requests with an empty key
        if creds["api_key"] or not preset.needs_key:
            return {"base_url": creds["base_url"] or preset.base_url,
                    "api_key": creds["api_key"] or "no-key",
                    "model": creds["model"], "provider": pid, "family": preset.family}
    s = get_settings()


    # send `max_tokens` — the compatible endpoints of Ollama / LM Studio **only accept `max_tokens`** and
    # **silently ignore** fields they do not recognise (sources in point 4 of the `llm.py` module docstring),
    # so sending only `max_completion_tokens` means **no cap at all**.
    # This is not "an endpoint you might configure": **the factory-default `llm_base_url` is
    # `127.0.0.1:11434/v1` — Ollama's port**.
    # Relying on this field rather than guessing from base_url: it is what the user picked, not sniffed.
    return {"base_url": cfg["local_base_url"] or s.llm_base_url,
            "api_key": cfg["local_api_key"] or s.llm_api_key,
            "model": cfg["local_model"] or s.llm_model, "provider": "local", "family": "local"}


def get_active_judge_config() -> dict:
    """Use the separate judge when fully configured; otherwise explicitly fall back to the current writing model."""
    s = get_settings()
    if s.judge_base_url and s.judge_model:
        return {"base_url": s.judge_base_url.rstrip("/"),
                "api_key": s.judge_api_key or "no-key",
                "model": s.judge_model, "provider": "judge", "independent": True}
    return {**get_active_llm_config(), "independent": False}


def llm_configured() -> dict:
    """"Has a model been configured" is a different question from "configured but unreachable"; the status
    bar must tell them apart (P19 #1 / P17 #1).

    Configured means: a preset is selected and has what it needs (a key if it requires one, a non-empty model
    name; `gpt` has a factory default model, so a key alone counts); or the "local model" entry has address +
    model on the settings page; or .env / the environment set `LLM_BASE_URL` (the dev-machine setup). None of
    those = factory default (localhost 11434, empty model) — the day-one user — and then the status bar / every
    AI button should say "no model configured -> open settings" rather than report an address as unreachable.
    `source` is the id of the configured entry (the old values 'gpt' / 'local' unchanged) or 'env' / 'default'.
    """
    from ..util.config import env_set
    from ..util.config import PROVIDERS
    cfg = get_provider_config()
    pid = cfg["provider"]
    preset = PROVIDERS.get(pid)
    if preset is not None and pid != "local":
        creds = get_provider_credentials(pid, cfg)
        if (creds["api_key"] or not preset.needs_key) and creds["model"]:
            return {"configured": True, "source": pid}
    if cfg["local_base_url"] and cfg["local_model"]:
        return {"configured": True, "source": "local"}
    if env_set("llm_base_url"):
        return {"configured": True, "source": "env"}
    return {"configured": False, "source": "default"}


def get_active_vision_config() -> dict:
    """Which endpoint vision actually uses: the address in the settings "Vision" field if filled; otherwise
    `VISION_BASE_URL` from .env (deployment override) if given; with neither, **follow the current writing
    model** (`follows_llm=True`) — a day-one user who configures one model gets vision too, no second setup."""
    from ..util.config import env_set
    cfg = get_provider_config()
    if cfg["vision_base_url"]:
        return {"base_url": cfg["vision_base_url"], "api_key": cfg["vision_api_key"] or "no-key",
                "model": cfg["vision_model"], "follows_llm": False}
    s = get_settings()
    if env_set("vision_base_url") and s.vision_base_url:
        return {"base_url": s.vision_base_url, "api_key": s.vision_api_key or "no-key",
                "model": s.vision_model, "follows_llm": False}
    return {**get_active_llm_config(), "follows_llm": True}


def get_asr_base_url() -> str:
    """Effective whisper.cpp server address: the Settings value if set, else `.env` (same idea as
    get_active_llm_config)."""
    return get_provider_config()["asr_base_url"] or get_settings().whisper_base_url


ASR_PROVIDERS = ("whisper", "assemblyai", "speechmatics")


def get_active_asr_config() -> dict:
    """Effective speech-to-text config: {provider, base_url, api_key, region}.

    Each field: the Settings value if set, else the `.env` deployment default. `base_url` is the
    whisper.cpp server address (hosted providers resolve their host from `region` in asr.py);
    `api_key` / `region` belong to the active hosted provider and are empty for whisper."""
    cfg = get_provider_config()
    s = get_settings()
    provider = (cfg["asr_provider"] or s.asr_provider or "whisper").strip().lower()
    if provider not in ASR_PROVIDERS:
        provider = "whisper"
    out = {"provider": provider, "base_url": cfg["asr_base_url"] or s.whisper_base_url,
           "api_key": "", "region": ""}
    if provider in ("assemblyai", "speechmatics"):
        out["api_key"] = cfg[f"{provider}_api_key"] or getattr(s, f"{provider}_api_key")
        out["region"] = cfg[f"{provider}_region"] or getattr(s, f"{provider}_region")
    return out


def record_harness_run(key: str, status: str, rounds: int,
                       final_scores: dict[str, int], weak_dimensions: list[str],
                       stopped: str = "", run_id: str = "",
                       tokens: int = 0, calls: int = 0) -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO harness_runs "
            "(id, key, status, rounds, final_scores, weak_dimensions, stopped, "
            "tokens, calls, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id or str(uuid.uuid4()), key, status, rounds,
             json.dumps(final_scores, ensure_ascii=False),
             json.dumps(weak_dimensions, ensure_ascii=False), stopped[:40],
             int(tokens), int(calls), _now()))


        c.execute("DELETE FROM harness_runs WHERE key=? AND id NOT IN ("
                  "SELECT id FROM harness_runs WHERE key=? ORDER BY created_at DESC, rowid DESC LIMIT 50)",
                  (key, key))


def record_harness_round(key: str, run_id: str, round_: int, scores: dict[str, int],
                         status: str, weakest: str, content_len: int,
                         facts_new: int = 0, facts_total: int = 0,
                         tool_calls: int = 0, repeat_calls: int = 0,
                         cached_calls: int = 0, superseded: int = 0,
                         revisions_proposed: int = 0,
                         revisions_dropped: int = 0,
                         depth_dropped: int = 0,
                         claim_atoms: int = -1,
                         fired_checks: str = "",
                         abstained: str = "",
                         cite_located: int = -1,
                         cite_marked: int = -1,
                         cite_matched: int = -1) -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO harness_rounds (id,key,run_id,round,scores,status,weakest,"
            "content_len,facts_new,facts_total,tool_calls,repeat_calls,"
            "cached_calls,superseded,revisions_proposed,revisions_dropped,"
            "depth_dropped,claim_atoms,fired_checks,abstained,"
            "cite_located,cite_marked,cite_matched,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), key, run_id, int(round_),
             json.dumps(scores, ensure_ascii=False), status, weakest,
             int(content_len), int(facts_new), int(facts_total),
             int(tool_calls), int(repeat_calls),
             int(cached_calls), int(superseded),
             int(revisions_proposed), int(revisions_dropped),
             int(depth_dropped), int(claim_atoms), str(fired_checks or ""),
             str(abstained or ""),
             int(cite_located), int(cite_marked), int(cite_matched), _now()))


        c.execute("DELETE FROM harness_rounds WHERE key=? AND id NOT IN ("
                  "SELECT id FROM harness_rounds WHERE key=? "
                  "ORDER BY created_at DESC, rowid DESC LIMIT 400)", (key, key))


def rounds_of_run(run_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM harness_rounds WHERE run_id=? ORDER BY round",
                         (run_id,)).fetchall()
    return [dict(r) | {"scores": json.loads(r["scores"] or "{}")} for r in rows]


def recent_harness_runs(key: str, limit: int = 3) -> list[dict]:
    with connect() as c:
        # created_at is second-precision (see _now()) -- several rounds can
        # legitimately finish within the same second, so break ties with
        # rowid (monotonic with insertion order) rather than leaving SQLite
        # to pick an arbitrary order among equal timestamps.
        rows = c.execute(
            "SELECT * FROM harness_runs WHERE key=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (key, limit)).fetchall()
    return [
        {
            "key": row["key"], "status": row["status"], "rounds": row["rounds"],
            "final_scores": json.loads(row["final_scores"]),
            "weak_dimensions": json.loads(row["weak_dimensions"]),
            "timestamp": row["created_at"],
            "stopped": row["stopped"] if "stopped" in row.keys() else "",
        }
        for row in rows
    ]


def sweep_orphan_assets(assets_dir: Path, min_age_days: int = 7) -> dict:
    if not assets_dir.is_dir():
        return {"removed": 0, "bytes": 0}
    now = datetime.now(timezone.utc).timestamp()
    removed = 0
    freed = 0
    with connect() as c:
        for entry in sorted(assets_dir.iterdir()):
            if not entry.is_file() or entry.name.startswith("."):
                continue
            if now - entry.stat().st_mtime < min_age_days * 86400:
                continue
            pat = f"%{entry.name}%"
            used = any(
                c.execute(f"SELECT 1 FROM {t} WHERE {col} LIKE ? LIMIT 1", (pat,)).fetchone()
                for t, col in (("notes", "content"), ("note_revisions", "content"), ("note_trash", "payload")))
            if used:
                continue
            try:
                size = entry.stat().st_size
                entry.unlink()
                removed += 1
                freed += size
            except OSError:
                pass
    return {"removed": removed, "bytes": freed}


def prune_job_payloads(jobs_dir: Path) -> int:
    if not jobs_dir.is_dir():
        return 0
    with connect() as c:
        keep = {r[0] for r in c.execute("SELECT payload_path FROM ingest_jobs WHERE status IN ('interrupted','queued','running','cancelling') AND payload_path<>''")}
    n = 0
    for f in jobs_dir.glob("*.json"):
        if str(f) not in keep and f.name[:-5] not in {Path(k).name[:-5] for k in keep}:
            f.unlink(missing_ok=True)
            n += 1
    return n


def sweep_orphan_plans() -> int:
    with connect() as c:
        n = c.execute("UPDATE writing_plans SET status='abandoned' WHERE status='active'"
                      " AND parent_note_id NOT IN (SELECT id FROM notes)").rowcount
        n += c.execute("DELETE FROM writing_sections WHERE note_id<>'' AND note_id NOT IN (SELECT id FROM notes)"
                       " AND plan_id IN (SELECT id FROM writing_plans WHERE status<>'active')").rowcount
        n += c.execute("DELETE FROM note_remotes WHERE note_id NOT IN (SELECT id FROM notes)"
                       " AND note_id NOT IN (SELECT note_id FROM note_trash)").rowcount
        return n


def sweep_orphan_jobs() -> int:
    with connect() as c:


        resumable = [r["id"] for r in c.execute(
            "SELECT id FROM ingest_jobs WHERE payload_path<>'' AND status NOT IN ('done','error','cancelled','interrupted')")]
        n = 0
        for jid in resumable:
            n += c.execute("UPDATE ingest_items SET status='queued', detail='' WHERE job_id=? AND status NOT IN ('done','failed','cancelled')",
                           (jid,)).rowcount
            c.execute("UPDATE ingest_jobs SET status='interrupted', detail='Service restarted; job interrupted and can be resumed' WHERE id=?", (jid,))
        n += c.execute(
            "UPDATE ingest_items SET status='failed', detail='Service restarted; job interrupted' WHERE status NOT IN ('done','failed','cancelled') AND job_id NOT IN (SELECT id FROM ingest_jobs WHERE status='interrupted')"
        ).rowcount
        c.execute("UPDATE ingest_jobs SET status='error', detail='Service restarted; job interrupted' WHERE status NOT IN ('done','error','cancelled','interrupted')")
    return n


# ------------------------------------------------------- skill configuration

def skill_configs(user_id: str) -> dict[str, dict]:
    """Our settings for each installed skill, keyed by directory name.

    Content is never in here -- it stays in the SKILL.md directory on disk.
    A skill with no row yet gets sensible defaults from the caller.
    """
    with connect() as conn:
        rows = conn.execute(
            "SELECT slug, enabled, scopes, sandbox, source, idx, seeded_sha FROM skill_config "
            "WHERE user_id = ?", (user_id,)).fetchall()
    return {
        r["slug"]: {
            "enabled": bool(r["enabled"]),
            "scopes": [s for s in (r["scopes"] or "").split(",") if s],
            "sandbox": r["sandbox"],
            "source": r["source"],
            "idx": r["idx"],
            "seeded_sha": r["seeded_sha"],
        }
        for r in rows
    }


def set_skill_config(user_id: str, slug: str, *, enabled: bool | None = None,
                     scopes: list[str] | None = None, sandbox: str | None = None,
                     source: str | None = None, idx: int | None = None,
                     seeded_sha: str | None = None) -> None:
    """Upsert one skill's configuration; unspecified fields keep their value.

    First-insert defaults are deliberately conservative: ``sandbox='none'``
    means an imported skill's scripts do not run until the user grants
    permission explicitly, the same way installing an app doesn't grant it
    the camera.
    """
    with connect() as conn:
        conn.execute("INSERT OR IGNORE INTO skill_config (user_id, slug) VALUES (?, ?)",
                     (user_id, slug))
        for column, value in (("enabled", None if enabled is None else int(enabled)),
                              ("scopes", None if scopes is None else ",".join(scopes)),
                              ("seeded_sha", seeded_sha),
                              ("sandbox", sandbox),
                              ("source", source),
                              ("idx", idx)):
            if value is not None:
                conn.execute(
                    f"UPDATE skill_config SET {column} = ? WHERE user_id = ? AND slug = ?",
                    (value, user_id, slug))
        conn.commit()


def delete_skill_config(user_id: str, slug: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM skill_config WHERE user_id=? AND slug=?",
                     (user_id, slug))
        conn.commit()


def save_snapshot(user_id: str, note_id: str, mode: str, round_idx: int,
                  state: str) -> str:
    run_id = uuid.uuid4().hex[:12]
    with connect() as c:
        if note_id:
            c.execute("DELETE FROM harness_snapshots WHERE user_id=? AND note_id=?",
                      (user_id, note_id))
        c.execute(
            "INSERT INTO harness_snapshots (id,user_id,note_id,mode,round,state,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (run_id, user_id, note_id, mode, round_idx, state, _now()))
        c.commit()
    return run_id


def get_snapshot(user_id: str, run_id: str) -> dict | None:
    """Scoped by user on purpose: a run id is the only thing the resume
    endpoint takes, and one user must not be able to resume another's run."""
    with connect() as c:
        row = c.execute(
            "SELECT * FROM harness_snapshots WHERE id=? AND user_id=?",
            (run_id, user_id)).fetchone()
    return dict(row) if row else None


def list_snapshots(user_id: str, limit: int = 20) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT id, note_id, mode, round, created_at FROM harness_snapshots "
            "WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, max(1, min(limit, 100)))).fetchall()
    return [dict(r) for r in rows]


def delete_snapshot(user_id: str, run_id: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM harness_snapshots WHERE id=? AND user_id=?",
                  (run_id, user_id))
        c.commit()


SNAPSHOT_MAX_AGE_DAYS = 7
USAGE_KEEP_DAYS = 90
JOB_KEEP_DAYS = 30
PLAN_KEEP_DAYS = 30


def vacuum_if_bloated(min_free_mb: float = 1.0, min_ratio: float = 0.25) -> dict:
    with connect() as c:
        page_size = c.execute("PRAGMA page_size").fetchone()[0]
        pages = c.execute("PRAGMA page_count").fetchone()[0]
        free = c.execute("PRAGMA freelist_count").fetchone()[0]
    before_mb = pages * page_size / 1024 / 1024
    free_mb = free * page_size / 1024 / 1024
    if pages == 0 or free_mb < min_free_mb or free / pages < min_ratio:
        return {"vacuumed": False, "before_mb": round(before_mb, 1), "free_mb": round(free_mb, 1)}
    conn = sqlite3.connect(_db_path())
    try:
        conn.isolation_level = None
        conn.execute("VACUUM")
        after = conn.execute("PRAGMA page_count").fetchone()[0] * page_size / 1024 / 1024
    finally:
        conn.close()
    return {"vacuumed": True, "before_mb": round(before_mb, 1), "after_mb": round(after, 1), "free_mb": round(free_mb, 1)}


def sweep_old_rows(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cut = lambda days: (now - timedelta(days=days)).isoformat()   # noqa: E731
    out = {}
    with connect() as c:
        out["usage"] = c.execute("DELETE FROM llm_usage WHERE created_at < ?", (cut(USAGE_KEEP_DAYS),)).rowcount
        old_jobs = [r["id"] for r in c.execute(
            "SELECT id FROM ingest_jobs WHERE status NOT IN ('queued','running') AND created_at < ?", (cut(JOB_KEEP_DAYS),))]
        if old_jobs:
            q = ",".join("?" * len(old_jobs))
            c.execute(f"DELETE FROM ingest_items WHERE job_id IN ({q})", old_jobs)
            c.execute(f"DELETE FROM ingest_jobs WHERE id IN ({q})", old_jobs)
        out["jobs"] = len(old_jobs)
        old_plans = [r["id"] for r in c.execute(
            "SELECT id FROM writing_plans WHERE status <> 'active' AND updated_at < ?", (cut(PLAN_KEEP_DAYS),))]
        if old_plans:
            q = ",".join("?" * len(old_plans))
            c.execute(f"DELETE FROM writing_sections WHERE plan_id IN ({q})", old_plans)
            c.execute(f"DELETE FROM writing_plans WHERE id IN ({q})", old_plans)
        out["plans"] = len(old_plans)
        c.commit()
    return out


def sweep_stale_snapshots(days: int = SNAPSHOT_MAX_AGE_DAYS) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with connect() as c:
        n = c.execute("DELETE FROM harness_snapshots WHERE created_at < ?", (cutoff,)).rowcount
        c.commit()
    return n


def prune_snapshots(user_id: str, keep: int = 20) -> int:
    """A paused run the user never came back to is dead weight. Keeping the
    most recent few per user is enough: resuming something from last month
    would apply month-old material to a note that has moved on."""
    with connect() as c:
        rows = c.execute(
            "SELECT id FROM harness_snapshots WHERE user_id=? "
            "ORDER BY created_at DESC", (user_id,)).fetchall()
        stale = [r["id"] for r in rows[keep:]]
        for run_id in stale:
            c.execute("DELETE FROM harness_snapshots WHERE id=?", (run_id,))
        c.commit()
    return len(stale)


ROUND_SKELETON_MISSING = (
    'Body generated this round',
    'Individual tool calls',
    'Skill list',
    'Failed or discarded revisions',
    'Reasons for strategy changes',
    'Previous-round diagnostics',
    'Live phase output',
    'Scorer judgments',


    'Missing capabilities this round',
)


def last_note_run_rounds(note_id: str) -> dict:
    key = f"note:{note_id}"
    with connect() as c:
        row = c.execute(
            "SELECT run_id, created_at FROM harness_rounds WHERE key=? "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1", (key,)).fetchone()
        runs_total = c.execute(
            "SELECT count(DISTINCT run_id) FROM harness_rounds WHERE key=?", (key,)).fetchone()[0]
        rounds_total = c.execute(
            "SELECT count(*) FROM harness_rounds WHERE key=?", (key,)).fetchone()[0]
        latest_run = c.execute(
            "SELECT * FROM harness_runs WHERE key=? "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1", (key,)).fetchone()
        recorded_runs = c.execute(
            "SELECT count(*) FROM harness_runs WHERE key=?", (key,)).fetchone()[0]


        latest_has_rounds = bool(latest_run and c.execute(
            "SELECT 1 FROM harness_rounds WHERE key=? AND run_id=? LIMIT 1",
            (key, latest_run["id"])).fetchone())
        if latest_run is not None and not latest_has_rounds and (
                row is None or latest_run["created_at"] >= row["created_at"]):
            return {
                "runId": latest_run["id"], "at": latest_run["created_at"],
                "status": latest_run["status"],
                "stopped": latest_run["stopped"] if "stopped" in latest_run.keys() else "",
                "rounds": [], "reason": "run_without_rounds",
                "runsTotal": max(runs_total, recorded_runs), "roundsTotal": rounds_total,
                "missing": list(ROUND_SKELETON_MISSING),
            }
        if row is None:
            return {"runId": "", "at": "", "status": "", "stopped": "", "rounds": [],
                    "reason": "no_rounds", "runsTotal": 0, "roundsTotal": 0,
                    "missing": list(ROUND_SKELETON_MISSING)}
        run_id = row["run_id"] or ""
        if not run_id:
            return {"runId": "", "at": row["created_at"], "status": "", "stopped": "",
                    "rounds": [], "reason": "no_run_id",
                    "runsTotal": runs_total, "roundsTotal": rounds_total,
                    "missing": list(ROUND_SKELETON_MISSING)}
        rows = c.execute(
            "SELECT * FROM harness_rounds WHERE key=? AND run_id=? ORDER BY round",
            (key, run_id)).fetchall()
        run = c.execute("SELECT * FROM harness_runs WHERE id=?", (run_id,)).fetchone()
    return {
        "runId": run_id,
        "at": row["created_at"],


        "status": (run["status"] if run is not None else ""),
        "stopped": (run["stopped"] if run is not None and "stopped" in run.keys() else ""),
        "rounds": [{
            "round": r["round"],


            "scores": json.loads(r["scores"] or "{}"),
            "status": r["status"],
            "weakest": r["weakest"],
            "contentLen": r["content_len"],
            "toolCalls": r["tool_calls"],
            "repeatCalls": r["repeat_calls"],
            "revisionsProposed": r["revisions_proposed"],
            "revisionsDropped": r["revisions_dropped"],
            "depthDropped": r["depth_dropped"],
            "factsNew": r["facts_new"],
            "factsTotal": r["facts_total"],


            "citeLocated": r["cite_located"],
            "citeMarked": r["cite_marked"],
            "citeMatched": r["cite_matched"],
            "firedChecks": r["fired_checks"] or "",
            "at": r["created_at"],
        } for r in rows],
        "reason": "ok",
        "runsTotal": runs_total,
        "roundsTotal": rounds_total,
        "missing": list(ROUND_SKELETON_MISSING),
    }
