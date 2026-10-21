"""JSON-first command line access to a running local NOTE workspace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import httpx

from .agent_client import WorkspaceClient


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="memoket-note", description=__doc__)
    p.add_argument("--url", help="Local backend origin (or MEMOKET_NOTE_URL)")
    p.add_argument("--user", help="Local workspace user ID (or MEMOKET_NOTE_USER)")
    sub = p.add_subparsers(dest="command", required=True)
    ls = sub.add_parser("list", help="List notes without downloading their bodies")
    ls.add_argument("--query", default="")
    for name in ("get", "export"):
        cmd = sub.add_parser(name, help="Read a note" if name == "get" else "Print one note as Markdown")
        cmd.add_argument("note_id")
    create = sub.add_parser("create", help="Create a note from a UTF-8 file or stdin")
    create.add_argument("--title", required=True)
    create.add_argument("--file", default="-", help="UTF-8 file; '-' reads stdin")
    recall = sub.add_parser("recall", help="Search saved memory with source evidence")
    recall.add_argument("query")
    recall.add_argument("--limit", type=int, default=8)
    revise = sub.add_parser("revise", help="Propose edits; never applies them to the note")
    revise.add_argument("note_id")
    revise.add_argument("--selection", required=True)
    revise.add_argument("--action", choices=("polish", "rewrite"), default="polish")
    job = sub.add_parser("job", help="Check an import or extraction job")
    job.add_argument("job_id")
    read = sub.add_parser("memoket-read", help="Call an allowlisted read tool through the official Memoket CLI")
    read.add_argument("tool")
    read.add_argument("--json", default="{}", dest="arguments")
    imp = sub.add_parser("memoket-import", help="Import a selected recording's brief as a source snapshot")
    imp.add_argument("conversation_id")
    imp.add_argument("--title", required=True)
    imp.add_argument("--to", choices=("notes", "both", "kb"), default="notes")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        client = WorkspaceClient(args.url, args.user)
        if args.command == "list":
            result = client.notes(args.query)
        elif args.command in {"get", "export"}:
            result = client.note(args.note_id)
            if args.command == "export":
                print(f"# {result['title']}\n\n{result['content']}")
                return 0
        elif args.command == "create":
            content = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
            result = client.create(args.title, content)
        elif args.command == "recall":
            result = client.recall(args.query, args.limit)
        elif args.command == "revise":
            result = client.revise(args.note_id, args.selection, args.action)
        elif args.command == "job":
            result = client.job(args.job_id)
        elif args.command == "memoket-read":
            arguments = json.loads(args.arguments)
            if not isinstance(arguments, dict):
                raise ValueError("--json must contain an object")
            result = client.memoket_read(args.tool, arguments)
        else:
            result = client.memoket_import(args.conversation_id, args.title, args.to)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, httpx.HTTPError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
