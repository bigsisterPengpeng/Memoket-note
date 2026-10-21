"""Retrieval at cluster grain, for writing.

Question-answering wants the narrowest topic that answers the question.
Writing wants everything about a subject at once: a section built from six
facts scattered over six sibling topics has nothing to say the second time
it is asked to write about that subject, so it says the first thing again in
different words -- which is what ``non_repetition`` has been measuring all
along.

So the same codebook is read two ways. ``kite_memory.recall`` stays exactly
as it is and keeps answering questions; this walks out from its hits into
the surrounding cluster and brings back the rest of the subject.

**Seeding still goes through the ordinary recall.** The clusters decide how
far to walk, never where to start -- a wrong cluster would otherwise be able
to replace the query's own answer instead of merely extending it.
"""

from __future__ import annotations

from . import clusters as _clusters

# How many facts the seeding recall asks for. Small: these only have to
# identify which subjects the query is about.
SEED_LIMIT = 6

# Per cluster, at most this many extra facts. Without a cap one large cluster
# fills the whole budget and the second subject in the query never appears.
PER_CLUSTER = 8


def recall_clustered(memory, query: str, *, limit: int = 12,
                     seed_limit: int = SEED_LIMIT, scope: str = "all",
                     per_cluster: int = PER_CLUSTER, evidence: bool = False,
                     entity_guard: bool = False) -> tuple[list[dict], list[str], float]:
    """``(fact rows, matched surface terms, milliseconds)`` -- recall's shape.

    Same tuple as ``UserMemory.recall`` on purpose: the caller decides which
    view it wants, and nothing downstream has to know which one it got.
    """
    seeds, terms, took = memory.recall(
        query, limit=seed_limit, scope=scope, evidence=evidence)
    store, _vocab = memory._index()
    groups = cached(memory)

    # A topic cluster is deliberately broad and can contain facts about
    # unrelated people or organisations. Expansion must preserve the subject
    # boundary established by the direct query hits.
    # Seeds are still the query's direct answer. When the strict writing path
    # enables this guard, expansion may add facts with no named entity, or
    # facts about an entity already present in a seed; it cannot introduce a
    # brand-new named subject merely because both facts share a broad topic.
    seed_entities: set[str] = set()
    if entity_guard:
        for row in seeds:
            fact = store.facts.get(row.get("id"))
            seed_entities.update(getattr(fact, "entities", ()) or ())

    out = list(seeds)
    seen = {row.get("id") for row in out}
    for cluster in _ordered(seeds, store, groups):
        added = 0
        for fact in _facts_of(cluster, store):
            if len(out) >= limit or added >= per_cluster:
                break
            if fact["id"] in seen:
                continue
            if (entity_guard and fact.get("entities")
                    and not (set(fact["entities"]) & seed_entities)):
                continue
            out.append(fact)
            seen.add(fact["id"])
            added += 1
        if len(out) >= limit:
            break
    return out[:limit], terms, took


def cached(memory) -> list[_clusters.Cluster]:
    """Clusters for this codebook, rebuilt when the file changes.

    Keyed on mtime, the same way ``UserMemory._index`` caches the parsed
    codebook: clustering is deterministic, so a stale result is only ever
    wrong when the data underneath it moved.
    """
    path = str(memory.path)
    mtime = memory.path.stat().st_mtime if memory.path.exists() else 0.0
    hit = _CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    store, _vocab = memory._index()
    built = _clusters.build(store)
    _CACHE[path] = (mtime, built)
    return built


_CACHE: dict[str, tuple[float, list[_clusters.Cluster]]] = {}


def _ordered(seeds: list[dict], store, groups: list[_clusters.Cluster]
             ) -> list[_clusters.Cluster]:
    """The clusters the seeds landed in, best-scoring seed first.

    Order matters because of the budget: the query's strongest hit should get
    its subject filled out before a weaker one does.
    """
    by_topic: dict[str, _clusters.Cluster] = {}
    for cluster in groups:
        for topic in cluster.topics:
            by_topic[topic] = cluster

    out: list[_clusters.Cluster] = []
    for row in seeds:
        fact = store.facts.get(row.get("id"))
        if not fact:
            continue
        for topic in fact.topics:
            cluster = by_topic.get(topic)
            if cluster is not None and cluster not in out:
                out.append(cluster)
    return out


def _facts_of(cluster: _clusters.Cluster, store) -> list[dict]:
    """A cluster's facts, most recent first.

    Recency is the same ordering ``recall`` applies within a hit set, so
    walking out from a hit does not silently change what "next" means.
    """
    rows = []
    for topic in cluster.topics:
        for fid in store.by_topic.get(topic, ()):
            fact = store.facts.get(fid)
            if fact is None:
                continue
            rows.append({"type": "fact", "id": fact.id, "unit": fact.unit,
                         "date": fact.when, "kind": fact.kind, "who": fact.who,
                         "conf": fact.conf, "text": fact.text,
                         "topics": list(fact.topics),
                         "entities": list(fact.entities)})
    rows.sort(key=lambda r: (r["date"] or "", r["id"]), reverse=True)
    return rows
