"""Content-addressed local assets associated with notes."""

from __future__ import annotations

from pathlib import Path

from ..util.config import get_settings


def assets_dir() -> Path:
    d = Path(get_settings().kite_data_dir) / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d
