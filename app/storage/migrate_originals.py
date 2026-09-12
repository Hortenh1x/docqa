"""Explicit, non-destructive copy of pre-existing originals into configured S3.

Run with writers stopped before enabling the independent-storage release target.
Existing local files remain in place; a failed copy stops without deleting originals.
"""

import json
import shutil
import tempfile
from pathlib import Path

from sqlalchemy import select

from app.db.models import Collection, Document
from app.db.sync import sync_session
from app.ingestion.mime import EXT_BY_MIME
from app.storage import get_storage
from app.storage.local import file_digest
from app.storage.s3 import S3Storage


def migrate_originals() -> int:
    storage = get_storage()
    if not isinstance(storage, S3Storage):
        raise RuntimeError("Configure versioned S3 before migrating original files")
    with sync_session() as db:
        references = db.execute(
            select(Collection.tenant_id, Document.sha256, Document.mime_type)
            .join(Document, Document.collection_id == Collection.id)
            .distinct()
        ).all()
    for tenant_id, digest, mime in references:
        ext = EXT_BY_MIME[mime]
        original = storage.path_for(str(tenant_id), digest, ext)
        if file_digest(original) != digest:
            raise RuntimeError("Existing original failed integrity verification")
        with tempfile.TemporaryDirectory(prefix="docqa-original-copy-") as directory:
            temporary = Path(directory) / "original"
            shutil.copyfile(original, temporary)
            storage.store(str(tenant_id), digest, ext, temporary)
        storage.verify_remote(str(tenant_id), digest, ext)
    return len(references)


if __name__ == "__main__":
    print(json.dumps({"verified_remote_originals": migrate_originals()}))
