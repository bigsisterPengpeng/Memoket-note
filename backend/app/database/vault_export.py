"""Non-destructive exports to an explicitly chosen local vault."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import threading
from urllib.parse import quote

from . import assets, exporters, store

_WRITE_LOCK = threading.RLock()


class VaultConflict(Exception):
    def __init__(self, path: str):
        super().__init__(path)
        self.path = path


def _target(vault: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Invalid export path: {relative}")
    target = vault
    for index, part in enumerate(path.parts):
        target /= part
        if target.is_symlink():
            raise ValueError(f"Symbolic links are not export destinations: {relative}")
        if target.exists() and not (target.is_file() if index == len(path.parts) - 1 else target.is_dir()):
            raise ValueError(f"The destination path is occupied: {relative}")
    return target


def _read(target: Path) -> bytes | None:
    try:
        return target.read_bytes()
    except FileNotFoundError:
        return None


def _install(vault: Path, relative: str, data: bytes, expected: bytes | None) -> None:
    target = _target(vault, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target = _target(vault, relative)
    descriptor, name = tempfile.mkstemp(prefix=".memoket-export-", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            if target.exists():
                os.chmod(temporary, stat.S_IMODE(target.stat().st_mode))
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        target = _target(vault, relative)
        if expected is None:
            try:
                # An exclusive link cannot replace a file created after preflight.
                os.link(temporary, target)
            except FileExistsError as exc:
                raise VaultConflict(relative) from exc
        else:
            if _read(target) != expected:
                raise VaultConflict(relative)
            os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _owned(previous: dict | None, vault: Path, path: str, content: bytes) -> bool:
    if not previous or previous.get("remote_path") != path:
        return False
    if previous.get("remote_rev") != str(vault):
        return False
    try:
        return store.content_sha(content.decode("utf-8")) == previous.get("remote_id")
    except UnicodeDecodeError:
        return False


def write_vault(user: str, vault: Path, files: list[exporters.ExportFile], *, force: bool = False) -> dict:
    vault = vault.resolve()
    written, skipped, conflicts, failed, urls = [], [], [], [], []
    assets_written = 0
    with _WRITE_LOCK:
        for file in files:
            try:
                target = _target(vault, file.path)
                current = _read(target)
                body = file.content.encode("utf-8")
                previous = store.get_remote(user, file.note_id, "obsidian") if file.note_id else None
                if current is not None and current != body and not force and not _owned(previous, vault, file.path, current):
                    raise VaultConflict(file.path)

                for name in sorted(file.assets):
                    relative = f"_assets/{name}"
                    source = assets.assets_dir() / name
                    if not source.is_file():
                        raise ValueError(f"Attachment not found: {relative}")
                    data = source.read_bytes()
                    existing = _read(_target(vault, relative))
                    if existing is not None and existing != data and not force:
                        raise VaultConflict(relative)
                    if existing != data:
                        _install(vault, relative, data, existing)
                        assets_written += 1
                if current == body:
                    if _read(_target(vault, file.path)) != current:
                        raise VaultConflict(file.path)
                    skipped.append(file.path)
                else:
                    _install(vault, file.path, body, current)
                    written.append(file.path)
                if file.note_id:
                    store.record_remote(user, file.note_id, "obsidian", remote_id=store.content_sha(file.content),
                                        remote_path=file.path, remote_rev=str(vault))
                    urls.append({"note_id": file.note_id, "title": file.title,
                                 "url": "obsidian://open?path=" + quote(str(target), safe="/")})
            except VaultConflict as exc:
                if exc.path not in conflicts:
                    conflicts.append(exc.path)
            except (OSError, ValueError) as exc:
                reason = exc.strerror if isinstance(exc, OSError) else str(exc)
                failed.append(f"{file.path}: {reason or 'Could not write this file'}")
    return {"written": len(written), "skipped": len(skipped), "assets_written": assets_written,
            "conflicts": conflicts, "failed": failed, "files": written[:50],
            "urls": urls[:50], "url": urls[0]["url"] if len(urls) == 1 else ""}
