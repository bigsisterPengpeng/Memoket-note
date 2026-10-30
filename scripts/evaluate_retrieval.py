"""Measure scoped recall on fictional sources without models or a personal library."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

PROJECTS = ("Maple", "Birch", "Cedar", "Willow", "Aspen", "Alder", "Hazel", "Rowan")
SCOPES = ("all", "notes", "imports", "meetings", "screen")


def seed(memory) -> list[dict]:
    root = ET.fromstring(memory.ensure().read_text())
    vocab, timeline = root.find("vocab"), root.find("timeline")
    cases = []
    for project in PROJECTS:
        code = project.lower()
        ET.SubElement(vocab, "topic", code=code, status="canonical", parents="project")
        sources = [
            (f"note-{code}-1", "2026-10-01", f"{project} labels approved."),
            (f"note-{code}-2", "2026-10-02", "The follow-up review is scheduled for Friday."),
            (f"md-{code}-1", "2026-10-03", f"{project} labels imported from a fictional vault."),
            (f"meeting-{code}-1", "2026-10-04", f"{project} labels reviewed in a fictional meeting."),
        ]
        sources += [(f"screen-{code}-{i}", "2026-10-20", f"{project} labels {project} labels {project} labels on a fictional screen.") for i in range(14)]
        for uid, date, text in sources:
            session = ET.SubElement(timeline, "session", id=uid, date=date, title=f"Fictional {project}", dur="1m")
            ET.SubElement(session, "line", id=f"{uid}-L1", who="user").text = text
            ET.SubElement(session, "fact", id=f"{uid}-F1", t=date, kind="decision", conf="high", topics=code, src=f"{uid}-L1").text = text
        for scope in SCOPES:
            # Independent ground truth: source membership and the query's wording.
            prefixes = {"all": ("note-", "md-", "meeting-"), "notes": ("note-",), "imports": ("md-",), "meetings": ("meeting-",), "screen": ("screen-",)}[scope]
            allowed = {f"{uid}-F1" for uid, _, _ in sources if uid.startswith(prefixes)}
            direct = allowed - {f"note-{code}-2-F1"}
            cases.append({"query": f"{project} labels", "scope": scope, "direct": direct, "cluster": allowed, "prefixes": prefixes})
    ET.ElementTree(root).write(memory.path, encoding="utf-8", xml_declaration=True)
    memory.invalidate()
    return cases


def percentile(values, quantile):
    return sorted(values)[max(0, int(len(values) * quantile + 0.999) - 1)]


def evaluate(memory, cases, iterations):
    from app.database.kb.recall import recall_clustered

    modes = {}
    for mode in ("direct", "cluster"):
        elapsed, hits, reciprocal, recall, precision, compliance = [], [], [], [], [], []
        first = time.perf_counter()
        for case in cases:
            def retrieve():
                if mode == "direct":
                    return memory.recall(case["query"], limit=2, scope=case["scope"], evidence=True)[0]
                return recall_clustered(memory, case["query"], limit=5, scope=case["scope"], evidence=True, entity_guard=True)[0]
            rows = retrieve()
            ids = [row["id"] for row in rows]
            wanted = case[mode]
            relevant = set(ids) & wanted
            hits.append(bool(relevant))
            reciprocal.append(next((1 / (index + 1) for index, fid in enumerate(ids) if fid in wanted), 0))
            recall.append(len(relevant) / len(wanted))
            precision.append(len(relevant) / len(ids) if ids else 0)
            compliance.append(all(row["unit"].startswith(case["prefixes"]) for row in rows))
            for _ in range(iterations):
                started = time.perf_counter()
                retrieve()
                elapsed.append((time.perf_counter() - started) * 1000)
        empty = memory.recall("Unseen satellite protocol", scope="notes", evidence=True)[0]
        modes[mode] = {
            "queries": len(cases), "limit": 2 if mode == "direct" else 5,
            "hit_rate": statistics.mean(hits), "mrr": statistics.mean(reciprocal),
            "mean_recall_at_limit": statistics.mean(recall),
            "mean_returned_precision": statistics.mean(precision),
            "scope_compliance_rate": statistics.mean(compliance),
            "unmatched_query_abstains": not empty,
            "warm_p50_ms": round(statistics.median(elapsed), 3),
            "warm_p95_ms": round(percentile(elapsed, 0.95), 3),
            "total_ms": round((time.perf_counter() - first) * 1000, 3),
        }
    return modes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, default=Path(__file__).resolve().parents[1] / "backend", help="Backend checkout to evaluate for revision comparisons")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 100:
        parser.error("iterations must be between 1 and 100")
    sys.path.insert(0, str(args.backend.resolve()))
    with tempfile.TemporaryDirectory(prefix="memoket-retrieval-eval-") as temporary:
        os.environ.update(KITE_DATA_DIR=temporary, MEMOKET_SKIP_TOPIC_SETTLE="1", LLM_API_KEY="fictional-evaluation", LLM_BASE_URL="http://127.0.0.1:9/v1")
        from app.database.kite.kite_memory import UserMemory

        memory = UserMemory("fictional-evaluation")
        cases = seed(memory)
        started = time.perf_counter()
        memory.recall(cases[0]["query"], limit=2, scope="notes", evidence=True)
        first_ms = (time.perf_counter() - started) * 1000
        results = {
            "dataset": "Fictional library pilots; 8 projects, 144 source-linked facts, 40 source/query cases",
            "provider_calls": 0, "iterations_per_case": args.iterations,
            "first_notes_query_ms": round(first_ms, 3),
            "metrics": evaluate(memory, cases, args.iterations),
            "limits": "Synthetic source-selection benchmark, not a semantic or live-model writing-quality benchmark. Recall is bounded by the return limit when a scope has more relevant facts than slots. Timing includes Python/KITE work on this host and is not an SLA.",
        }
        memory.invalidate()
    output = json.dumps(results, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
