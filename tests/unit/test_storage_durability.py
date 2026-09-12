"""Acknowledged originals survive cache loss; failures never masquerade as uploads."""

import hashlib
import io
import uuid
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.storage.local import LocalStorage

TENANT = str(uuid.uuid4())
DATA = b"private original document"
SHA = hashlib.sha256(DATA).hexdigest()


def test_local_store_rejects_corrupt_source_and_repairs_corrupt_existing(tmp_path):
    from app.storage.errors import StorageUnavailableError

    store = LocalStorage(tmp_path / "files")
    src = tmp_path / "upload"
    src.write_bytes(b"damaged")
    with pytest.raises(StorageUnavailableError):
        store.store(TENANT, SHA, ".txt", src)
    src.write_bytes(DATA)
    dest = store.path_for(TENANT, SHA, ".txt")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"damaged existing")
    store.store(TENANT, SHA, ".txt", src)
    assert dest.read_bytes() == DATA
    assert not src.exists()
    assert dest.stat().st_mode & 0o777 == 0o600


def test_local_fsync_failure_does_not_acknowledge_or_discard_source(tmp_path, monkeypatch):
    from app.storage.errors import StorageUnavailableError

    store = LocalStorage(tmp_path / "files")
    src = tmp_path / "upload"
    src.write_bytes(DATA)

    def fail(_):
        raise OSError("disk unavailable")

    monkeypatch.setattr("os.fsync", fail)
    with pytest.raises(StorageUnavailableError):
        store.store(TENANT, SHA, ".txt", src)
    assert src.read_bytes() == DATA


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.versioning = "Enabled"
        self.ack_version = "v1"
        self.calls = []
        self.versions = {}
        self.delete_result = {"DeleteMarker": True, "VersionId": "delete-v2"}
        self.list_object_versions = Mock(return_value={"DeleteMarkers": []})

    def get_bucket_versioning(self, **kw):
        return {"Status": self.versioning}

    def put_object(self, **kw):
        self.calls.append(kw.copy())
        self.objects[kw["Key"]] = kw["Body"].read()
        self.versions[(kw["Key"], self.ack_version)] = self.objects[kw["Key"]]
        return {"VersionId": self.ack_version}

    def get_object(self, **kw):
        if kw["Key"] not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[kw["Key"]]), "VersionId": "v1"}

    def delete_object(self, **kw):
        self.calls.append(kw.copy())
        del self.objects[kw["Key"]]
        return self.delete_result


def s3_store(tmp_path):
    from app.storage.s3 import S3Storage

    remote = MemoryS3()
    return S3Storage(LocalStorage(tmp_path / "cache"), "originals", remote), remote


def test_s3_ack_requires_version_and_cache_loss_recovers_exact_bytes(tmp_path):
    from app.storage.errors import StorageUnavailableError

    store, remote = s3_store(tmp_path)
    src = tmp_path / "upload"
    src.write_bytes(DATA)
    store.store(TENANT, SHA, ".txt", src)
    assert remote.calls[0]["Key"] == f"{TENANT}/{SHA}.txt"
    assert "ACL" not in remote.calls[0]
    assert remote.calls[0]["ChecksumSHA256"]
    dest = store.path_for(TENANT, SHA, ".txt")
    dest.unlink()
    assert store.path_for(TENANT, SHA, ".txt").read_bytes() == DATA
    # Another tenant cannot retrieve this object even when its hash is known.
    with pytest.raises(StorageUnavailableError):
        store.path_for(str(uuid.uuid4()), SHA, ".txt")


@pytest.mark.parametrize("versioning,version", [("Suspended", "v1"), ("Enabled", "null")])
def test_s3_does_not_acknowledge_unversioned_original(tmp_path, versioning, version):
    from app.storage.errors import StorageUnavailableError

    store, remote = s3_store(tmp_path)
    remote.versioning, remote.ack_version = versioning, version
    src = tmp_path / "upload"
    src.write_bytes(DATA)
    with pytest.raises(StorageUnavailableError):
        store.store(TENANT, SHA, ".txt", src)
    assert src.exists()


def test_s3_corrupt_download_never_enters_cache(tmp_path):
    from app.storage.errors import StorageUnavailableError

    store, remote = s3_store(tmp_path)
    remote.objects[f"{TENANT}/{SHA}.txt"] = b"corrupt"
    with pytest.raises(StorageUnavailableError):
        store.path_for(TENANT, SHA, ".txt")
    assert not store.cache.path_for(TENANT, SHA, ".txt").exists()


def test_s3_delete_uses_marker_not_permanent_version_delete(tmp_path):
    store, remote = s3_store(tmp_path)
    src = tmp_path / "upload"
    src.write_bytes(DATA)
    store.store(TENANT, SHA, ".txt", src)
    store.delete(TENANT, SHA, ".txt")
    assert remote.calls[-1] == {"Bucket": "originals", "Key": f"{TENANT}/{SHA}.txt"}
    assert not store.cache.path_for(TENANT, SHA, ".txt").exists()
    assert remote.versions[(f"{TENANT}/{SHA}.txt", "v1")] == DATA
    remote.list_object_versions.assert_not_called()


@pytest.fixture
def s3_original(tmp_path):
    store, remote = s3_store(tmp_path)
    src = tmp_path / "upload"
    src.write_bytes(DATA)
    store.store(TENANT, SHA, ".txt", src)
    return store, remote, store.cache.path_for(TENANT, SHA, ".txt")


def test_s3_delete_missing_header_confirms_exact_latest_marker(s3_original):
    store, remote, cached = s3_original
    key = f"{TENANT}/{SHA}.txt"
    remote.delete_result = {"VersionId": "delete-v2"}
    remote.list_object_versions.return_value = {
        "DeleteMarkers": [{"Key": key, "VersionId": "delete-v2", "IsLatest": True}],
        "Versions": [{"Key": key, "VersionId": "v1", "IsLatest": False}],
    }

    store.delete(TENANT, SHA, ".txt")

    remote.list_object_versions.assert_called_once_with(
        Bucket="originals", Prefix=key, MaxKeys=1000
    )
    assert not cached.exists()
    assert remote.versions[(key, "v1")] == DATA
    assert remote.calls[-1] == {"Bucket": "originals", "Key": key}


@pytest.mark.parametrize("header", [False, None, "true", 1])
def test_s3_delete_explicit_invalid_marker_never_uses_fallback(s3_original, header):
    from app.storage.errors import StorageUnavailableError

    store, remote, cached = s3_original
    remote.delete_result = {"VersionId": "delete-v2", "DeleteMarker": header}
    with pytest.raises(StorageUnavailableError):
        store.delete(TENANT, SHA, ".txt")
    remote.list_object_versions.assert_not_called()
    assert cached.read_bytes() == DATA


@pytest.mark.parametrize("version", [None, "", "null"])
@pytest.mark.parametrize("header_present", [False, True])
def test_s3_delete_requires_durable_version_before_fallback(s3_original, version, header_present):
    from app.storage.errors import StorageUnavailableError

    store, remote, cached = s3_original
    remote.delete_result = {"VersionId": version}
    if header_present:
        remote.delete_result["DeleteMarker"] = True
    with pytest.raises(StorageUnavailableError):
        store.delete(TENANT, SHA, ".txt")
    remote.list_object_versions.assert_not_called()
    assert cached.read_bytes() == DATA


@pytest.mark.parametrize(
    "listing",
    [
        {},
        {"DeleteMarkers": []},
        {
            "DeleteMarkers": [
                {"Key": f"{TENANT}/{SHA}.txt.extra", "VersionId": "delete-v2", "IsLatest": True}
            ]
        },
        {
            "DeleteMarkers": [
                {"Key": f"{TENANT}/{SHA}.txt", "VersionId": "other-version", "IsLatest": True}
            ]
        },
        {
            "DeleteMarkers": [
                {"Key": f"{TENANT}/{SHA}.txt", "VersionId": "delete-v2", "IsLatest": False}
            ]
        },
        {"DeleteMarkers": [{"Key": f"{TENANT}/{SHA}.txt", "VersionId": "delete-v2"}]},
        {"Versions": [{"Key": f"{TENANT}/{SHA}.txt", "VersionId": "delete-v2", "IsLatest": True}]},
    ],
    ids=[
        "missing",
        "empty",
        "prefix-collision",
        "wrong-version",
        "not-latest",
        "unknown-latest",
        "not-marker",
    ],
)
def test_s3_delete_unconfirmed_listing_keeps_cache(s3_original, listing):
    from app.storage.errors import StorageUnavailableError

    store, remote, cached = s3_original
    remote.delete_result = {"VersionId": "delete-v2"}
    remote.list_object_versions.return_value = listing
    with pytest.raises(StorageUnavailableError):
        store.delete(TENANT, SHA, ".txt")
    remote.list_object_versions.assert_called_once()
    assert cached.read_bytes() == DATA


@pytest.mark.parametrize(
    "error",
    [
        ClientError({"Error": {"Code": "AccessDenied"}}, "ListObjectVersions"),
        EndpointConnectionError(endpoint_url="https://synthetic.invalid"),
    ],
)
def test_s3_delete_listing_failure_keeps_cache(s3_original, error):
    from app.storage.errors import StorageUnavailableError

    store, remote, cached = s3_original
    remote.delete_result = {"VersionId": "delete-v2"}
    remote.list_object_versions.side_effect = error
    with pytest.raises(StorageUnavailableError):
        store.delete(TENANT, SHA, ".txt")
    remote.list_object_versions.assert_called_once()
    assert cached.read_bytes() == DATA


def test_s3_delete_follows_both_pagination_markers(s3_original):
    store, remote, cached = s3_original
    key = f"{TENANT}/{SHA}.txt"
    remote.delete_result = {"VersionId": "delete-v2"}
    remote.list_object_versions.side_effect = [
        {"IsTruncated": True, "NextKeyMarker": key, "NextVersionIdMarker": "page-one"},
        {"DeleteMarkers": [{"Key": key, "VersionId": "delete-v2", "IsLatest": True}]},
    ]
    store.delete(TENANT, SHA, ".txt")
    assert remote.list_object_versions.call_count == 2
    remote.list_object_versions.assert_called_with(
        Bucket="originals",
        Prefix=key,
        MaxKeys=1000,
        KeyMarker=key,
        VersionIdMarker="page-one",
    )
    assert not cached.exists()
    assert remote.versions[(key, "v1")] == DATA


@pytest.mark.parametrize(
    "page",
    [
        {"IsTruncated": True},
        {"IsTruncated": True, "NextKeyMarker": "key"},
        {"IsTruncated": True, "NextKeyMarker": "key", "NextVersionIdMarker": "version"},
    ],
    ids=["missing-cursors", "missing-version-cursor", "repeated-cursors"],
)
def test_s3_delete_unsafe_pagination_stops_and_keeps_cache(s3_original, page):
    from app.storage.errors import StorageUnavailableError

    store, remote, cached = s3_original
    remote.delete_result = {"VersionId": "delete-v2"}
    remote.list_object_versions.return_value = page
    with pytest.raises(StorageUnavailableError):
        store.delete(TENANT, SHA, ".txt")
    assert 1 <= remote.list_object_versions.call_count <= 2
    assert cached.read_bytes() == DATA


def test_s3_delete_bounds_version_listing_and_keeps_cache(s3_original):
    from app.storage.errors import StorageUnavailableError

    store, remote, cached = s3_original
    remote.delete_result = {"VersionId": "delete-v2"}
    remote.list_object_versions.side_effect = [
        {
            "IsTruncated": True,
            "NextKeyMarker": f"{TENANT}/{SHA}.txt",
            "NextVersionIdMarker": str(index),
        }
        for index in range(10)
    ]
    with pytest.raises(StorageUnavailableError):
        store.delete(TENANT, SHA, ".txt")
    assert remote.list_object_versions.call_count == 10
    assert cached.read_bytes() == DATA


@pytest.mark.parametrize("equivalent", [False, True])
def test_local_store_preserves_original_when_source_is_destination(tmp_path, equivalent):
    store = LocalStorage(tmp_path / "files")
    dest = store.path_for(TENANT, SHA, ".txt")
    dest.parent.mkdir(parents=True)
    dest.write_bytes(DATA)
    source = dest.parent / ".." / dest.parent.name / dest.name if equivalent else dest

    store.store(TENANT, SHA, ".txt", source)

    assert dest.read_bytes() == DATA
    assert source.read_bytes() == DATA
    assert dest.stat().st_mode & 0o777 == 0o600


def upload_fixture(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from fastapi import UploadFile

    from app.ingestion import service
    from app.storage.usage import ACCOUNT_STORAGE_LIMIT_BYTES, StorageUsage

    root = tmp_path / "new-parent" / "files"
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(storage_dir=root, max_upload_bytes=1024, demo_mode=False),
    )
    monkeypatch.setattr(service, "get_storage", lambda: LocalStorage(root))
    monkeypatch.setattr(service, "lock_tenant_files", AsyncMock())
    monkeypatch.setattr(
        service,
        "storage_usage",
        AsyncMock(
            return_value=StorageUsage(
                used_bytes=0,
                limit_bytes=ACCOUNT_STORAGE_LIMIT_BYTES,
                remaining_bytes=ACCOUNT_STORAGE_LIMIT_BYTES,
                document_count=0,
            )
        ),
    )
    monkeypatch.setattr(service.ingest_document, "delay", Mock())
    db = SimpleNamespace(
        scalar=AsyncMock(side_effect=[False, "personal", None]),
        add=Mock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    collection = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.UUID(TENANT), read_only=False)
    upload = UploadFile(file=io.BytesIO(DATA), filename="original.txt")
    return service, root, db, collection, upload


async def test_first_upload_syncs_all_new_storage_ancestors_before_commit(tmp_path, monkeypatch):
    from app.storage import local

    service, root, db, collection, upload = upload_fixture(tmp_path, monkeypatch)
    events = []
    real_sync = local.sync_directory

    def sync(path):
        real_sync(path)
        events.append(("sync", path))

    async def commit():
        events.append(("commit", None))

    monkeypatch.setattr(local, "sync_directory", sync)
    db.commit.side_effect = commit

    await service.save_upload(db, collection, upload)

    committed = events.index(("commit", None))
    for parent in (tmp_path, root.parent, root):
        assert ("sync", parent) in events[:committed], f"New entry in {parent} was not durable"
    assert LocalStorage(root).path_for(TENANT, SHA, ".txt").read_bytes() == DATA
    db.commit.assert_awaited_once()


async def test_first_upload_parent_sync_failure_never_commits(tmp_path, monkeypatch):
    from app.storage import local
    from app.storage.errors import StorageUnavailableError

    service, root, db, collection, upload = upload_fixture(tmp_path, monkeypatch)
    real_sync = local.sync_directory

    def sync(path):
        if path == tmp_path:
            raise OSError("Synthetic ancestor fsync failure")
        real_sync(path)

    monkeypatch.setattr(local, "sync_directory", sync)

    with pytest.raises(StorageUnavailableError):
        await service.save_upload(db, collection, upload)

    db.commit.assert_not_awaited()
    assert not LocalStorage(root).path_for(TENANT, SHA, ".txt").exists()


def test_directory_retry_resyncs_ancestor_left_by_failed_attempt(tmp_path, monkeypatch):
    from app.storage import local
    from app.storage.errors import StorageUnavailableError

    storage = LocalStorage(tmp_path / "new-parent" / "files")
    source = tmp_path / "upload.txt"
    source.write_bytes(DATA)
    real_sync = local.sync_directory
    synced = []
    fail_once = True

    def sync(path):
        nonlocal fail_once
        if path == tmp_path and fail_once:
            fail_once = False
            raise OSError("Synthetic fsync failure")
        real_sync(path)
        synced.append(path)

    monkeypatch.setattr(local, "sync_directory", sync)
    with pytest.raises(StorageUnavailableError):
        storage.store(TENANT, SHA, ".txt", source)
    assert source.exists()
    storage.store(TENANT, SHA, ".txt", source)
    assert tmp_path in synced
    assert storage.path_for(TENANT, SHA, ".txt").read_bytes() == DATA
