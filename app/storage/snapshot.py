"""Hydrate and verify committed originals and OCR copies before an offline backup."""

from sqlalchemy import select

from app.db.models import Collection, Document
from app.db.sync import sync_session
from app.ingestion.mime import EXT_BY_MIME, SEARCHABLE_PDF_EXT
from app.storage import get_storage
from app.storage.errors import StorageUnavailableError
from app.storage.local import file_digest


def verify_original_cache() -> int:
    with sync_session() as db:
        references = db.execute(
            select(
                Collection.tenant_id,
                Document.sha256,
                Document.mime_type,
                Document.searchable_sha256,
            ).join(Document, Document.collection_id == Collection.id)
        ).all()
    storage = get_storage()
    for tenant_id, digest, mime, searchable_digest in references:
        path = storage.path_for(str(tenant_id), digest, EXT_BY_MIME[mime])
        if file_digest(path) != digest:
            raise StorageUnavailableError("Backup original integrity verification failed.")
        if searchable_digest is not None:
            path = storage.path_for(str(tenant_id), searchable_digest, SEARCHABLE_PDF_EXT)
            if file_digest(path) != searchable_digest:
                raise StorageUnavailableError(
                    "Backup searchable PDF integrity verification failed."
                )
    return len(references)


if __name__ == "__main__":
    print(f"Verified {verify_original_cache()} committed originals for backup.")
