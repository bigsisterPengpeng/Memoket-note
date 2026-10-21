"""Inventory literal Han characters in version-controlled project text.

Include non-ignored new files so the report covers pending changes. Unlike the
frontend ratchet, this audit includes configuration, documentation and fixtures.
The report contains paths and counts, never source excerpts or fixture contents.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HAN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".mts", ".mjs", ".cjs", ".js", ".css", ".sh", ".html"}


def category(path: str) -> str:
    if path.startswith("frontend/src/i18n/zh/") or path in {
        "backend/app/util/i18n_zh.py", "desktop/src/i18n.ts",
    }:
        return "translations"
    if path.startswith(("backend/tests/fixtures/", "shared/")):
        return "fixtures and shared contracts"
    if Path(path).suffix in SOURCE_SUFFIXES:
        return "source and tests"
    if Path(path).suffix in {".md", ".txt", ".jsonl", ".tsv"}:
        return "documentation and text data"
    return "configuration and other text"


def inventory() -> list[dict[str, str | int]]:
    tracked = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT,
    ).decode("utf-8").split("\0")
    rows = []
    for name in sorted(set(tracked) - {""}):
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lines = source.splitlines()
        count = sum(bool(HAN.search(line)) for line in lines)
        if count:
            rows.append({"path": name, "category": category(name), "lines": count})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the complete inventory as JSON")
    parser.add_argument("--strict", action="store_true", help="Fail if any inventoried text contains Han characters")
    parser.add_argument("--limit", type=int, default=20, help="Number of files shown in the text report")
    parser.add_argument("--english-source", action="store_true", help="Reject literal Han characters outside dedicated translation dictionaries")
    args = parser.parse_args()
    rows = inventory()
    total = sum(int(row["lines"]) for row in rows)
    if args.json:
        print(json.dumps({"files": len(rows), "lines": total, "matches": rows}, indent=2))
    else:
        print(f"Literal Han characters: {total} lines in {len(rows)} files")
        counts: Counter[str] = Counter()
        for row in rows:
            counts[str(row["category"])] += int(row["lines"])
        for group, count in counts.most_common():
            print(f"  {group}: {count} lines")
        for row in sorted(rows, key=lambda item: -int(item["lines"]))[:max(0, args.limit)]:
            print(f"  {row['lines']:>6}  {row['path']}")
    violations = [row for row in rows if row["category"] != "translations"]
    return int((args.strict and bool(rows)) or (args.english_source and bool(violations)))


if __name__ == "__main__":
    raise SystemExit(main())
