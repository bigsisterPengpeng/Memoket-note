"""Read recording sources through the official Memoket CLI, without copying its credentials."""

from __future__ import annotations

import json
import shutil
import subprocess

from ..util.config import get_settings


READ_TOOLS = frozenset({"list_conversations", "search_recordings", "get_conversations",
                        "get_transcripts", "get_transcripts_by_participant", "get_summaries", "get_brief"})
MAX_RESPONSE_BYTES = 2_000_000


class ConnectorError(ValueError):
    pass


def executable() -> str:
    path = shutil.which(get_settings().memoket_cli)
    if not path:
        raise ConnectorError("Install @memoket-ai/cli and run 'memoket login' in Terminal. Set MEMOKET_CLI if it is outside the backend PATH.")
    if path.lower().endswith((".cmd", ".bat")):
        raise ConnectorError("Batch launchers are not supported. Set MEMOKET_CLI to a native executable, or connect an external agent to Memoket's remote MCP.")
    return path


def _run(arguments: list[str]) -> str:
    try:
        result = subprocess.run([executable(), *arguments], stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ConnectorError("Memoket CLI could not finish. Check installation, network and 'memoket doctor'.") from exc
    if result.returncode:
        # Do not expose account content, OAuth responses or tokens from CLI diagnostics.
        raise ConnectorError("Memoket CLI call failed. Run 'memoket login' or 'memoket doctor' in Terminal, then retry.")
    if len(result.stdout) > MAX_RESPONSE_BYTES:
        raise ConnectorError("Memoket returned too much data. Narrow the query or request a smaller page.")
    return result.stdout.decode("utf-8")


def status() -> dict:
    try:
        version = _run(["--version"]).strip()
        return {"available": True, "version": version[:80], "tools": sorted(READ_TOOLS),
                "message": "CLI found. Search to check your existing Memoket login."}
    except ConnectorError as exc:
        return {"available": False, "message": str(exc), "tools": sorted(READ_TOOLS)}


def availability() -> dict:
    """Check installation without starting the CLI or reading an account."""
    try:
        executable()
        return {"available": True, "reason": ""}
    except ConnectorError as exc:
        return {"available": False, "reason": str(exc)}


def read(tool: str, arguments: dict) -> dict:
    if tool not in READ_TOOLS:
        raise ConnectorError("Only advertised Memoket recording read tools are allowed")
    payload = json.dumps(arguments, ensure_ascii=False, allow_nan=False)
    if len(payload) > 32_000:
        raise ConnectorError("Tool arguments are too large")
    try:
        data = json.loads(_run(["call", tool, "--json", payload]))
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, ConnectorError):
            raise
        raise ConnectorError("Memoket CLI returned an invalid JSON response") from exc
    if not isinstance(data, dict):
        raise ConnectorError("Memoket CLI response must be a JSON object")
    if data.get("isError") or data.get("is_error") or data.get("error"):
        raise ConnectorError("Memoket could not read this source. Check access and recording ID.")
    return data


def _readable(value, depth: int = 0) -> str:
    """Preserve report fields without depending on an undocumented output schema."""
    if depth > 12:
        raise ConnectorError("Memoket report nesting exceeds the import limit")
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                return _readable(json.loads(value), depth + 1)
            except json.JSONDecodeError:
                pass
        return value
    if isinstance(value, list):
        return "\n\n".join(_readable(item, depth + 1) for item in value)
    if isinstance(value, dict):
        if "structuredContent" in value:
            return _readable(value["structuredContent"], depth + 1)
        if value.get("type") == "text" and isinstance(value.get("text"), str):
            return _readable(value["text"], depth + 1)
        return "\n\n".join(f"**{key.replace('_', ' ')}**\n\n{_readable(item, depth + 1)}"
                            for key, item in value.items() if item is not None and item != "")
    return json.dumps(value, ensure_ascii=False)


def _has_more(value) -> bool:
    if isinstance(value, dict):
        return (bool(value.get("has_more")) or value.get("next_offset") not in (None, -1, "", 0)
                or any(_has_more(item) for item in value.values()))
    if isinstance(value, list):
        return any(_has_more(item) for item in value)
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            return _has_more(json.loads(value))
        except json.JSONDecodeError:
            return False
    return False


def _has_text(value) -> bool:
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                return _has_text(json.loads(value))
            except json.JSONDecodeError:
                pass
        return bool(value.strip())
    if isinstance(value, list):
        return any(_has_text(item) for item in value)
    if isinstance(value, dict):
        metadata = {"type", "conversation_id", "conversation_ids", "id", "title", "next_offset", "offset", "has_more"}
        return any(_has_text(item) for key, item in value.items() if key not in metadata)
    return False


def brief_snapshot(conversation_id: str) -> str:
    data = read("get_brief", {"conversation_ids": [conversation_id]})
    if _has_more(data):
        raise ConnectorError("This report has additional pages. Read them with memoket-read before importing the complete material manually.")
    body = _readable(data).strip()
    if not _has_text(data):
        raise ConnectorError("No report body was returned for this recording")
    return (f"Source: Memoket recording `{conversation_id}`\n\n"
            "Imported brief/report snapshot. Recording date is not inferred from the import date. Summary text can omit details; read the transcript before relying on an exact quote.\n\n"
            + body)
