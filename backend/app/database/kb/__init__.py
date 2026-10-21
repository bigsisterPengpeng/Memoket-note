"""Knowledge-base capabilities that sit above KITE but below any endpoint.

KITE owns the codebook: facts, topics, entities, retrieval. What lives here
is everything this product needs *on top of* that and KITE has no opinion
about -- clustering topics for writing, and judging an extraction before it
is kept.
"""

from .clusters import Cluster, build

__all__ = ["Cluster", "build"]
