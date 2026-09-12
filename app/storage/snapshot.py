"""Hydrate and verify all committed originals before a quiesced offline backup."""

from sqlalchemy import select

from app.db.models import Collection, Document
from app.db.sync import sync_session
from app.ingestion.mime import EXT_BY_MIME
from app.storage import get_storage
from app.storage.errors import StorageUnavailableError
from app.storage.local import file_digest


def verify_original_cache() -> int:
    with sync_session() as db:
        references = db.execute(
            select(Collection.tenant_id, Document.sha256, Document.mime_type).join(
                Document, Document.collection_id == Collection.id
            )
        ).all()
    storage = get_storage()
    for tenant_id, digest, mime in references:
        path = storage.path_for(str(tenant_id), digest, EXT_BY_MIME[mime])
        if file_digest(path) != digest:
            raise StorageUnavailableError("Backup original integrity verification failed.")
    return len(references)


if __name__ == "__main__":
    print(f"Verified {verify_original_cache()} committed originals for backup.")
