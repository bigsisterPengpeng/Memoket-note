"""Local export uses fictional notes and disposable vaults."""

import pytest
from fastapi.testclient import TestClient

from app.database import assets, exporters, store
from app.main import app

USER = "fictional-vault"


@pytest.fixture()
def vault(tmp_path):
    target = tmp_path / "vault"
    target.mkdir()
    return target


def export(vault, note, *, force=False):
    response = TestClient(app).post("/api/export/obsidian", json={
        "vault_dir": str(vault), "note_ids": [note["id"]], "force": force,
    }, headers={"X-User-Id": USER})
    assert response.status_code == 200, response.text
    return response.json()


def test_first_export_preserves_an_existing_untracked_file(vault):
    note = store.create_note(USER, "Maple report", "A fictional draft.")
    target = vault / "Maple report.md"
    original = b"# Existing local work\r\n\r\nKeep this unrelated draft.\r\n"
    target.write_bytes(original)
    result = export(vault, note)
    assert result["written"] == 0 and result["conflicts"] == [target.name]
    assert target.read_bytes() == original
    assert store.get_remote(USER, note["id"], "obsidian") is None


def test_repeat_export_updates_owned_content_but_preserves_external_edits(vault):
    note = store.create_note(USER, "Maple report", "The fictional team chose amber labels.")
    assert export(vault, note)["written"] == 1
    target = vault / "Maple report.md"
    first = target.read_bytes()
    result = export(vault, note)
    assert result["skipped"] == 1 and target.read_bytes() == first
    store.update_note(USER, note["id"], title=note["title"], content="The fictional team chose blue labels.")
    assert export(vault, note)["written"] == 1
    assert b"blue labels" in target.read_bytes()
    target.write_text("Edited in the fictional vault.")
    assert export(vault, note)["conflicts"] == [target.name]
    assert target.read_text() == "Edited in the fictional vault."
    assert export(vault, note, force=True)["written"] == 1
    assert b"blue labels" in target.read_bytes()


def test_export_to_another_vault_requires_fresh_overwrite_authority(vault, tmp_path):
    note = store.create_note(USER, "Maple report", "First fictional draft.")
    assert export(vault, note)["written"] == 1
    other = tmp_path / "other-vault"
    other.mkdir()
    # A copied old export does not establish ownership of another destination.
    copied = (vault / "Maple report.md").read_bytes()
    (other / "Maple report.md").write_bytes(copied)
    store.update_note(USER, note["id"], title=note["title"], content="Updated fictional draft.")
    result = export(other, note)
    assert result["conflicts"] == ["Maple report.md"]
    assert (other / "Maple report.md").read_bytes() == copied


def test_unchanged_export_restores_a_missing_attachment(vault, tmp_path, monkeypatch):
    source = tmp_path / "source-assets"
    source.mkdir()
    name = "a" * 24 + ".png"
    (source / name).write_bytes(b"fictional-image-bytes")
    monkeypatch.setattr(assets, "assets_dir", lambda: source)
    note = store.create_note(USER, "Maple figure", f"![Fictional diagram](/api/assets/{name})")
    assert export(vault, note)["written"] == 1
    target = vault / "_assets" / name
    target.unlink()
    result = export(vault, note)
    assert result["skipped"] == 1 and result["assets_written"] == 1
    assert target.read_bytes() == b"fictional-image-bytes"


def test_first_export_can_replace_a_regular_file_only_when_requested(vault):
    note = store.create_note(USER, "Maple report", "An explicitly chosen fictional replacement.")
    target = vault / "Maple report.md"
    target.write_text("Existing fictional draft.")
    result = export(vault, note, force=True)
    assert result["written"] == 1 and not result["conflicts"]
    assert "fictional replacement" in target.read_text()
    receipt = store.get_remote(USER, note["id"], "obsidian")
    assert receipt["remote_rev"] == str(vault.resolve())


def test_legacy_receipt_needs_one_confirmed_update_to_bind_its_vault(vault):
    note = store.create_note(USER, "Maple report", "First fictional version.")
    file = exporters.render_tree(USER)[0]
    (vault / file.path).write_text(file.content)
    store.record_remote(USER, note["id"], "obsidian", remote_id=store.content_sha(file.content), remote_path=file.path)
    store.update_note(USER, note["id"], note["title"], "Second fictional version.")
    assert export(vault, note)["conflicts"] == [file.path]
    assert (vault / file.path).read_text() == file.content
    assert export(vault, note, force=True)["written"] == 1
    assert "Second fictional version" in (vault / file.path).read_text()


def test_identical_untracked_export_is_safe_to_adopt(vault):
    note = store.create_note(USER, "Maple report", "A fictional draft.")
    file = exporters.render_tree(USER)[0]
    (vault / file.path).write_text(file.content)
    before = (vault / file.path).stat().st_mtime_ns
    result = export(vault, note)
    assert result["skipped"] == 1
    assert (vault / file.path).stat().st_mtime_ns == before
    assert store.get_remote(USER, note["id"], "obsidian")["remote_rev"] == str(vault.resolve())


def test_conflicting_attachment_blocks_the_note_until_reviewed(vault, tmp_path, monkeypatch):
    source = tmp_path / "source-assets"
    source.mkdir()
    name = "b" * 24 + ".png"
    (source / name).write_bytes(b"fictional-new-image")
    monkeypatch.setattr(assets, "assets_dir", lambda: source)
    (vault / "_assets").mkdir()
    target = vault / "_assets" / name
    target.write_bytes(b"existing-image-to-keep")
    note = store.create_note(USER, "Maple figure", f"![Fictional diagram](/api/assets/{name})")
    result = export(vault, note)
    assert result["conflicts"] == [f"_assets/{name}"]
    assert target.read_bytes() == b"existing-image-to-keep"
    assert not (vault / "Maple figure.md").exists()
    assert store.get_remote(USER, note["id"], "obsidian") is None
    assert export(vault, note, force=True)["written"] == 1
    assert target.read_bytes() == b"fictional-new-image"


def test_missing_source_attachment_reports_failure_without_creating_note(vault, tmp_path, monkeypatch):
    monkeypatch.setattr(assets, "assets_dir", lambda: tmp_path)
    note = store.create_note(USER, "Maple figure", f"![Missing fictional diagram](/api/assets/{'c' * 24}.png)")
    result = export(vault, note)
    assert result["written"] == 0 and len(result["failed"]) == 1
    assert not (vault / "Maple figure.md").exists()
    assert store.get_remote(USER, note["id"], "obsidian") is None


def test_write_failure_preserves_file_receipt_and_removes_temporary_file(vault, monkeypatch):
    import errno
    from app.database import vault_export

    note = store.create_note(USER, "Maple report", "First fictional version.")
    export(vault, note)
    target = vault / "Maple report.md"
    before = target.read_bytes()
    receipt = store.get_remote(USER, note["id"], "obsidian")
    store.update_note(USER, note["id"], note["title"], "Second fictional version.")
    def full_disk(_):
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(vault_export.os, "fsync", full_disk)
    result = export(vault, note)
    assert result["written"] == 0 and "No space left" in result["failed"][0]
    assert target.read_bytes() == before
    assert store.get_remote(USER, note["id"], "obsidian") == receipt
    assert not list(vault.glob(".memoket-export-*"))


@pytest.mark.parametrize("existing", [False, True])
def test_a_file_changed_after_preflight_is_not_overwritten(vault, monkeypatch, existing):
    from app.database import vault_export

    note = store.create_note(USER, "Maple report", "First fictional version.")
    target = vault / "Maple report.md"
    if existing:
        export(vault, note)
        store.update_note(USER, note["id"], note["title"], "Second fictional version.")
    original = vault_export._install
    def concurrent_edit(root, path, data, expected):
        target.write_bytes(b"A fictional concurrent edit.")
        original(root, path, data, expected)
    monkeypatch.setattr(vault_export, "_install", concurrent_edit)
    result = export(vault, note)
    assert result["written"] == 0 and result["conflicts"] == [target.name]
    assert target.read_bytes() == b"A fictional concurrent edit."
    assert not list(vault.glob(".memoket-export-*"))


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("parent_link", [False, True])
def test_export_does_not_follow_destination_symlinks(vault, tmp_path, force, parent_link):
    outside = tmp_path / "outside"
    outside.mkdir()
    original = outside / "Maple report.md"
    original.write_bytes(b"Unrelated fictional content.")
    note = store.create_note(USER, "Maple report", "A fictional export.")
    if parent_link:
        (vault / "Maple report").symlink_to(outside, target_is_directory=True)
        store.create_note(USER, "Child", "A fictional child.", parent_id=note["id"])
    else:
        (vault / "Maple report.md").symlink_to(original)
    result = export(vault, note, force=force)
    assert result["written"] == 0 and "Symbolic links" in result["failed"][0]
    assert original.read_bytes() == b"Unrelated fictional content."


def test_an_occupied_directory_does_not_abort_other_notes(vault):
    first = store.create_note(USER, "Maple report", "First fictional draft.")
    second = store.create_note(USER, "Cedar report", "Second fictional draft.")
    (vault / "Maple report.md").mkdir()
    response = TestClient(app).post("/api/export/obsidian", json={"vault_dir": str(vault)}, headers={"X-User-Id": USER})
    assert response.status_code == 200
    result = response.json()
    assert result["written"] == 1 and len(result["failed"]) == 1
    assert (vault / "Maple report.md").is_dir()
    assert (vault / "Cedar report.md").is_file()
    assert store.get_remote(USER, first["id"], "obsidian") is None
    assert store.get_remote(USER, second["id"], "obsidian")


def test_clone_markers_also_preserve_unrelated_existing_files(vault, monkeypatch):
    note = store.create_note(USER, "Maple report", "A fictional draft.")
    monkeypatch.setattr(exporters, "render_tree", lambda *args: [exporters.ExportFile(path="Maple.link.txt", content="A fictional clone marker.")])
    marker = vault / "Maple.link.txt"
    marker.write_bytes(b"Existing unrelated text.")
    assert export(vault, note)["conflicts"] == [marker.name]
    assert marker.read_bytes() == b"Existing unrelated text."
