# Source-scoped memory retrieval

The source selector beside the draft applies to keyword recall, subject-cluster
expansion and the writing agent's memory tools. `All (excluding screen)` keeps
screen activity out; `Screen activity only` opts into that source explicitly.

Source selection now happens before candidate limits, ranking, pagination and
cluster expansion. KITE builds a cached, read-only view containing the selected
source units. Its normal loader rebuilds posting lists and lexical statistics;
compiled session queries and their stage bindings execute against that same
view. Known topic and entity labels remain valid query anchors even when other
sources repeat them heavily. Generic prose terms retain full-corpus frequency
checks to avoid widening a query to unrelated subjects. The persisted codebook
and full-library browser are unchanged. Changing or removing a source invalidates these views along with the full index.

This is a writing-material filter, not an access-control boundary. Explicitly
provided document content, selected tray material and existing citations are
separate inputs. Library browsing and explicit fact/source-ID inspection can
still show every source, so existing citations can be verified after changing the discovery
filter.

## Reproduce the synthetic comparison

From the repository root, using the backend's installed dependencies:

```sh
backend/.venv/bin/python scripts/evaluate_retrieval.py
```

To compare another checkout without modifying it:

```sh
backend/.venv/bin/python scripts/evaluate_retrieval.py \
  --backend /path/to/baseline/backend --output /tmp/baseline-retrieval.json
```

The script creates and removes its own temporary library. It does not call a
model, read an installed desktop profile or need an account. The independently
authored dataset contains 144 source-linked facts across eight fictional library
pilots, with notes, Markdown imports, meeting records and screen activity. Forty
query/scope cases deliberately put stronger out-of-scope matches ahead of the
wanted material. Follow-up facts test useful expansion beyond an exact keyword.
An unmatched query checks abstention.

## October 30, 2026 result

Compared with revision `7962fe8` on the same macOS arm64 host, using ten warm
repetitions per case:

| Metric | Previous | Source-scoped retrieval |
|---|---:|---:|
| Direct recall: queries with a relevant result | 20% | 100% |
| Direct recall: mean reciprocal rank | 0.20 | 1.00 |
| Cluster expansion: queries with no out-of-scope result | 20% | 100% |
| Cluster expansion: mean precision of returned facts | 44% | 100% |
| Direct recall: warm p95 | 1.40 ms | 1.14 ms |
| Cluster expansion: warm p95 | 1.94 ms | 1.38 ms |

Direct recall already removed out-of-scope rows at the end, so it appeared
compliant while returning no useful facts in four of five scopes. Expansion
could find a valid seed and then add facts from excluded sources. The new view
fixes both paths. Regression tests also cover a pool with 820 stronger excluded
facts, raw-line fallback, scoped counts and pagination, source inspection,
compiled two-stage queries, empty scopes and source deletion.

These are targeted regression results, not a general relevance benchmark, a
semantic-search comparison or a writing-quality score. Return limits bound
recall when a scope has more relevant facts than available slots. Timing is a
local observation rather than an SLA; view construction and tokenizer startup
make the first query more expensive. No vector service or dependency was added.
