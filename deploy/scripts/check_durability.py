"""Read-only release gate for configured synchronous PostgreSQL and versioned originals.

Run inside the application image. This checks mechanisms, not physical host independence;
the deployment inventory and an independent-host exercise must establish that separately.
"""

import json

from sqlalchemy import select, text

from app.config import get_settings
from app.db.models import Collection, Document
from app.db.sync import sync_session
from app.ingestion.mime import EXT_BY_MIME
from app.storage import get_storage


def check() -> dict[str, bool]:
    settings = get_settings()
    if settings.storage_provider != "s3":
        raise RuntimeError("Independent versioned original storage is required")
    storage = get_storage()
    # The public StorageProtocol has no provider configuration mutations.
    from app.storage.s3 import S3Storage

    assert isinstance(storage, S3Storage)
    storage._versioned()
    with sync_session() as db:
        state = db.execute(
            text(
                "SELECT current_setting('synchronous_commit'), "
                "current_setting('synchronous_standby_names'), "
                "current_setting('fsync'), current_setting('full_page_writes'), "
                "pg_is_in_recovery()"
            )
        ).one()
        if (
            state[0] not in ("on", "remote_apply")
            or not state[1]
            or state[2:4] != ("on", "on")
            or state[4]
        ):
            raise RuntimeError("PostgreSQL synchronous durability settings are not active")
        standby = db.scalar(
            text(
                "SELECT count(*) FROM pg_stat_replication WHERE application_name='docqa_standby' "
                "AND state='streaming' AND sync_state IN ('sync', 'quorum')"
            )
        )
        if not standby:
            raise RuntimeError("The required synchronous standby is not streaming")
        references = db.execute(
            select(Collection.tenant_id, Document.sha256, Document.mime_type)
            .join(Document, Document.collection_id == Collection.id)
            .distinct()
        ).all()
    for tenant_id, digest, mime in references:
        storage.verify_remote(str(tenant_id), digest, EXT_BY_MIME[mime])
    return {"synchronous_standby": True, "versioned_originals": True}


if __name__ == "__main__":
    print(json.dumps(check()))
