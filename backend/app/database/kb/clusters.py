"""Group topics into clusters, so writing can retrieve at a coarser grain.

**The problem, measured.** The writing codebook has 196 topics with a median
of 10 facts each and 51% at or below 10; the original codebook has 117 with a
median of 35 and only 21% at or below 10. Fine topics are what makes
question-answering precise, and they are exactly what makes writing repeat
itself: a section's worth of material is spread across six topics, retrieval
returns one of them, and the round says the same thing again from a new angle.

This is a real trade-off, not a bug. GraphRAG's answer is the one taken here:
**keep the fine topics for retrieval and build a coarse layer on top of
them.** Facts stay where they are; clusters are a view.

**Why co-occurrence and not the names.** The obvious cheap grouping is the
shared prefix -- ``product_design``, ``product_strategy``, ``product_*``.
Measured on the real codebook it barely moves anything: 196 topics collapse
to 114 prefixes, the median goes from 10 to 12.5, and 46% are still at or
below 10, because 77 prefixes have exactly one topic. The fragmentation is
semantic, not lexical: ``international_school_admissions``, ``english_*`` and
``career_*`` are one subject and share no prefix.

Topics that keep turning up in the same conversations, on the other hand, do
belong together. On the real data the top pairs by overlap are
``property_sale ~ property_rental``, ``academic_performance ~
education_abroad``, and ``odi_application ~ offshore_fundraising ~
red_chip_architecture`` -- all correct, all invisible to prefix matching.

**No model call and no graph database.** Deterministic all the way through,
including tie-breaking, so the same codebook always produces the same
clusters and a change in them means the data changed.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

# A cluster is finished when it holds this many facts. Chosen from the
# measured distribution: the original codebook -- the one whose topics are
# *not* fragmented -- has a median of 35 facts per topic, so a group below
# roughly this size is the thing being fixed rather than a legitimate small
# subject.
FACT_FLOOR = 25

# Two topics must share at least this many conversations before their overlap
# counts at all. One shared meeting is coincidence: every codebook has a
# meeting where two unrelated subjects came up once.
MIN_SHARED_UNITS = 2

# And the overlap has to be a real fraction of both, not two large topics
# brushing past each other.
MIN_JACCARD = 0.10


@dataclass(frozen=True)
class Cluster:
    """A coarse group. ``topics`` is what retrieval expands it back into."""

    key: str                       # stable id: the largest member's name
    label: str                     # what a person reads
    topics: tuple[str, ...]
    facts: int
    merged: bool = False           # False = a topic big enough to stand alone


@dataclass
class _Group:
    topics: set[str] = field(default_factory=set)
    facts: int = 0
    # Per-topic conversation sets, kept separate rather than unioned. The
    # union is what causes chaining: a group of four topics has four times
    # the chances of brushing against an unrelated fifth, and the overlap is
    # computed against a set none of its members owns.
    units: dict[str, set[str]] = field(default_factory=dict)


def build(store, *, floor: int = FACT_FLOOR,
          min_shared: int = MIN_SHARED_UNITS,
          min_jaccard: float = MIN_JACCARD) -> list[Cluster]:
    """Cluster the topics in one KITE ``Store``.

    Greedy agglomeration: repeatedly merge the pair with the strongest
    overlap **where at least one side is still under the floor**, and stop
    when no such pair is left. A topic that is already large is never dragged
    into a merge by a small neighbour -- that would make the coarse layer
    coarser than the material warrants, which is the failure mode on the
    other side of this trade-off.
    """
    groups = _seed(store)
    if not groups:
        return []

    while True:
        best = _best_pair(groups, floor, min_shared, min_jaccard)
        if best is None:
            break
        _score, a, b = best
        groups[a].topics |= groups[b].topics
        groups[a].units.update(groups[b].units)
        groups[a].facts += groups[b].facts
        del groups[b]

    out = []
    for key in sorted(groups):
        g = groups[key]
        names = tuple(sorted(g.topics))
        out.append(Cluster(key=_key_of(names, store), label=_label_of(names),
                           topics=names, facts=g.facts, merged=len(names) > 1))
    # Biggest first: that is the order the writing side wants to read them in.
    return sorted(out, key=lambda c: (-c.facts, c.key))


# ------------------------------------------------------------------ internals


def _seed(store) -> dict[str, _Group]:
    """One group per topic, carrying the conversations it was drawn from."""
    groups: dict[str, _Group] = {}
    for name, fact_ids in store.by_topic.items():
        units: set[str] = set()
        for fid in fact_ids:
            fact = store.facts.get(fid)
            if not fact or not fact.src:
                continue
            line = store.lines.get(fact.src[0])
            if line:
                units.add(line.unit)
        if units:                       # no provenance, nothing to cluster on
            groups[name] = _Group(topics={name}, facts=len(fact_ids),
                                  units={name: units})
    return groups


def _best_pair(groups: dict[str, _Group], floor: int, min_shared: int,
               min_jaccard: float):
    """The strongest eligible merge, or None.

    **Complete linkage**: the score of two groups is the *weakest* overlap
    between any member of one and any member of the other. Single linkage --
    "it matched one member, let it in" -- chains: measured on the real
    codebook it put ``family_finance`` into a cluster about a child's
    schooling, and ``financial_reporting`` into one about recording features,
    neither of which it actually overlapped with. Requiring every pair to
    hold means a topic joins a cluster only if it belongs with all of it.

    Ties break on the group names so the result never depends on dict order.
    """
    best = None
    for a, b in itertools.combinations(sorted(groups), 2):
        ga, gb = groups[a], groups[b]
        if ga.facts >= floor and gb.facts >= floor:
            continue                    # both already stand on their own
        link = _linkage(ga, gb)
        if link is None:
            continue
        jaccard, shared = link
        if shared < min_shared or jaccard < min_jaccard:
            continue
        candidate = (jaccard, shared, a, b)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    return (best[0], best[2], best[3]) if best else None


def _linkage(ga: _Group, gb: _Group) -> tuple[float, int] | None:
    """The weakest member-to-member overlap between two groups."""
    worst: tuple[float, int] | None = None
    for ua in ga.units.values():
        for ub in gb.units.values():
            shared = len(ua & ub)
            score = (shared / len(ua | ub), shared)
            if worst is None or score < worst:
                worst = score
    return worst


def _key_of(names: tuple[str, ...], store) -> str:
    """The largest member names the cluster.

    A generated name ("cluster_7") would be stable only as long as nothing
    else changes; naming it after its dominant topic means a reader who knows
    the topics recognises the cluster on sight.
    """
    return max(names, key=lambda n: (len(store.by_topic.get(n, ())), n))


def _label_of(names: tuple[str, ...]) -> str:
    if len(names) == 1:
        return names[0]
    head = sorted(names, key=lambda n: (-len(n), n))[0]
    return f"{head} +{len(names) - 1}"
