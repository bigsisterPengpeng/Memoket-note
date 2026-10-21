"""Per-harness hook implementations.

One module per harness. Everything these modules have in common already lives
in the loop or in middleware -- if two of them grow the same code, that is the
signal to promote it, not to copy it a third time.
"""
