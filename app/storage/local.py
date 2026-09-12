"""Local-disk storage."""

import hashlib
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from app.config import get_settings
from app.storage.base import StorageProtocol
from app.storage.errors import StorageUnavailableError


def object_key(tenant_id: str, sha256: str, ext: str) -> str:
    """Only server-generated content addresses can become paths or remote keys."""
    if str(uuid.UUID(tenant_id)) != tenant_id or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise StorageUnavailableError("Invalid document storage address.")
    if ext not in (".pdf", ".docx", ".md", ".txt"):
        raise StorageUnavailableError("Invalid document storage format.")
    return f"{tenant_id}/{sha256}{ext}"


def file_digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_directory(path: Path) -> None:
    # An existing entry may belong to a concurrent creator or an earlier failed
    # fsync. Reconfirm ancestors on retries; existence alone is not durability.
    path = path.absolute()
    if path.parent == path:
        return
    durable_directory(path.parent)
    path.mkdir(mode=0o700, exist_ok=True)
    sync_directory(path.parent)


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, tenant_id: str, sha256: str, ext: str) -> Path:
        return self.root / object_key(tenant_id, sha256, ext)

    def store(self, tenant_id: str, sha256: str, ext: str, src: Path) -> None:
        dest = self.path_for(tenant_id, sha256, ext)
        temporary: Path | None = None
        try:
            if file_digest(src) != sha256:
                raise StorageUnavailableError("Document integrity verification failed.")
            source_is_destination = src.resolve() == dest.resolve()
            durable_directory(dest.parent)
            # Copy in the destination filesystem, then fsync and rename atomically.
            # Retain the caller's source until every durability operation succeeds.
            with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as out:
                temporary = Path(out.name)
                with src.open("rb") as source:
                    shutil.copyfileobj(source, out)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, dest)
            sync_directory(dest.parent)
            if not source_is_destination:
                src.unlink(missing_ok=True)
        except OSError:
            raise StorageUnavailableError("Could not durably store the document.") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def delete(self, tenant_id: str, sha256: str, ext: str) -> None:
        path = self.path_for(tenant_id, sha256, ext)
        try:
            if path.exists():
                path.unlink()
                sync_directory(path.parent)
        except OSError:
            raise StorageUnavailableError("Could not remove the cached document.") from None


def get_storage() -> StorageProtocol:
    settings = get_settings()
    local = LocalStorage(settings.storage_dir)
    if settings.storage_provider == "s3":
        from app.storage.s3 import create_s3_storage

        return create_s3_storage(settings, local)
    return local
