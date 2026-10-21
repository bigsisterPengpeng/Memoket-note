'Regression tests for kite private api.'

from __future__ import annotations

import pytest


@pytest.mark.parametrize("module, name, why", [
    ("memoket_kite.pipeline.extract", "_consolidation_round_votes",
     "Consolidation vote parsing must agree with the upstream engine."),
    ("memoket_kite.storage", "_verify_loadable",
     "Verify that the persisted codebook can be loaded before replacing it."),
])
def test_the_private_names_we_borrow_still_exist(module, name, why):
    import importlib

    mod = importlib.import_module(module)
    assert hasattr(mod, name), f"Missing upstream API {module}.{name}: {why} Review the pinned KITE adapter before updating the engine."
