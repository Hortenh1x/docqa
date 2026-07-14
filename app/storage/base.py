"""File storage behind a Protocol — local disk today, S3/MinIO later without a rewrite.

Files are addressed by content: ``{tenant_id}/{sha256}{ext}``. The stored name is always
generated; the user-supplied filename lives only in the database.
"""

from pathlib import Path
from typing import Protocol


class StorageProtocol(Protocol):
    def store(self, tenant_id: str, sha256: str, ext: str, src: Path) -> None:
        """Move ``src`` into the store (no-op if the content already exists)."""
        ...

    def path_for(self, tenant_id: str, sha256: str, ext: str) -> Path: ...

    def delete(self, tenant_id: str, sha256: str, ext: str) -> None: ...
