"""Start the bundled FastAPI backend.

PyInstaller launches an executable, so parse host/port arguments here and start
uvicorn programmatically. Dynamic KITE imports are collected in backend.spec.
"""

from __future__ import annotations

import argparse
import multiprocessing
import sys


def main() -> None:
    # Frozen child processes re-enter this module. Initialize multiprocessing
    # support before importing application code to avoid recursive process starts.
    multiprocessing.freeze_support()

    ap = argparse.ArgumentParser(prog="memoket-note-backend")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    import uvicorn

    from app.main import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    sys.exit(main())
