"""Isolate each test's SQLite database and KITE library from development data.

Set the data directory before application imports so modules that bind settings
at import time also write only to disposable storage.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

# Configure skills, assets, backups and jobs before any application import.
# Environment settings take precedence over the local .env file.
_TMP_DATA = tempfile.mkdtemp(prefix="memoket-tests-")
os.environ.setdefault("KITE_DATA_DIR", _TMP_DATA)
atexit.register(lambda: shutil.rmtree(_TMP_DATA, ignore_errors=True))
# Disable startup topic migration so TestClient instances cannot alter shared
# corpora between cases. Migration tests call the function explicitly.
os.environ.setdefault("MEMOKET_SKIP_TOPIC_SETTLE", "1")

import pytest  # noqa: E402

from app.database import store
from app.database.kite import kite_memory
from app.util.config import get_settings


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_db_path", lambda: tmp_path / "notes.sqlite3")
    # UserMemory must use a temporary codebook as well as a temporary database.
    real = get_settings()
    monkeypatch.setattr(kite_memory, "get_settings", lambda: real.model_copy(update={"kite_data_dir": tmp_path / "kite"}))
    yield


@pytest.fixture(autouse=True)
def _no_journey_sweep(monkeypatch):
    """Disable wall-clock retention cleanup for date-based activity fixtures.

    Otherwise fixed historical dates eventually expire during unrelated tests.
    Retention tests request this fixture and invoke the yielded real function.
    """
    from app.routers import journey as J

    real = J._sweep_if_due
    monkeypatch.setattr(J, "_sweep_if_due", lambda user: None)
    yield real
