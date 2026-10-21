"""Reject local data, internal records and recognizable secrets in a publication tree.

Inspect tracked and non-ignored files. Findings contain paths and rule names only;
never include matched secret values. Run again in the final publication checkout.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PREFIXES = (
    ".local/", "backend/data/", "desktop/out/", "outputs/", "docs/_research/",
    "docs/walkthrough-logs/",
)
PRIVATE_FILES = {
    "TRACELOG.md", "docs/TRACELOG-product.md", "docs/TRACELOG-harness.md",
    "docs/TRACELOG-trilium.md", "backend/tests/fixtures/memory_sample_corpus.json",
    "backend/tests/fixtures/memory_sample.jsonl",
}
SECRET_PATTERNS = {
    "github-token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b"),
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "service-token": re.compile(r"\b(?:sk_live_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{24,}|AKIA[A-Z0-9]{16})\b"),
}
LOCAL_PATH = re.compile(r"(?:/Users/[A-Za-z0-9_.-]+/|[A-Z]:\\Users\\[^\\\s]+\\)")
DATA_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".aiff", ".wav", ".pem", ".key", ".p12", ".pfx"}


def candidates() -> list[str]:
    raw = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT,
    )
    return sorted(set(raw.decode("utf-8").split("\0")) - {""})


def audit() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for name in candidates():
        path = ROOT / name
        if not path.exists():
            continue
        pure = PurePosixPath(name)
        rules = set()
        if path.is_symlink():
            rules.add("symlink-needs-review")
        elif path.is_file():
            if name.startswith(PRIVATE_PREFIXES) or name in PRIVATE_FILES:
                rules.add("internal-record-or-private-data")
            if pure.name == ".env" or (pure.name.startswith(".env.") and pure.suffix != ".example"):
                rules.add("environment-secrets-file")
            if pure.suffix.lower() in DATA_SUFFIXES:
                rules.add("database-audio-or-key-material")
            if path.stat().st_size >= 50 * 1024 * 1024:
                rules.add("large-file-needs-review")
            try:
                source = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                source = ""
            for rule, pattern in SECRET_PATTERNS.items():
                if pattern.search(source):
                    rules.add(rule)
            if LOCAL_PATH.search(source):
                rules.add("personal-absolute-path")
        for rule in sorted(rules):
            findings.append({"path": name, "rule": rule})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit all path-only findings as JSON")
    parser.add_argument("--limit", type=int, default=20, help="Maximum findings shown in text output")
    args = parser.parse_args()
    findings = audit()
    if args.json:
        print(json.dumps({"findings": findings, "passed": not findings}, indent=2))
    else:
        print(f"Publication audit: {len(findings)} finding(s)")
        for rule, count in Counter(row["rule"] for row in findings).most_common():
            print(f"  {rule}: {count}")
        for row in findings[:max(0, args.limit)]:
            print(f"  {row['path']}: {row['rule']}")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
