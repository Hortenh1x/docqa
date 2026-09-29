"""Quiesced backups recover every committed object from a cold remote cache."""

import hashlib
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.storage import snapshot
from app.storage.errors import StorageUnavailableError
from tests.unit.test_storage_durability import TENANT, s3_store


@pytest.mark.parametrize("derivative", [b"searchable pdf", None, b"corrupt"])
def test_snapshot_hydrates_and_verifies_searchable_pdf(tmp_path, monkeypatch, derivative):
    original = b"image original"
    original_sha = hashlib.sha256(original).hexdigest()
    searchable_sha = hashlib.sha256(b"searchable pdf").hexdigest()
    store, remote = s3_store(tmp_path)
    remote.objects[f"{TENANT}/{original_sha}.png"] = original
    if derivative is not None:
        remote.objects[f"{TENANT}/{searchable_sha}.ocr.pdf"] = derivative

    def execute(statement):
        values = {
            "tenant_id": TENANT,
            "sha256": original_sha,
            "mime_type": "image/png",
            "searchable_sha256": searchable_sha,
        }
        row = tuple(values[column.key] for column in statement.selected_columns)
        return SimpleNamespace(all=lambda: [row])

    @contextmanager
    def session():
        yield SimpleNamespace(execute=execute)

    monkeypatch.setattr(snapshot, "sync_session", session)
    monkeypatch.setattr(snapshot, "get_storage", lambda: store)
    if derivative == b"searchable pdf":
        assert snapshot.verify_original_cache() == 1
        assert store.cache.path_for(TENANT, searchable_sha, ".ocr.pdf").read_bytes() == derivative
    else:
        with pytest.raises(StorageUnavailableError):
            snapshot.verify_original_cache()
