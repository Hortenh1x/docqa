"""Versioned private originals; local files are a replaceable parser/download cache."""

import base64
import hashlib
import tempfile
from pathlib import Path
from typing import Any, Protocol, cast

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings
from app.storage.errors import StorageUnavailableError
from app.storage.local import LocalStorage, durable_directory, file_digest, object_key


class S3Client(Protocol):
    def get_bucket_versioning(self, **kwargs: Any) -> dict[str, Any]: ...
    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...
    def get_object(self, **kwargs: Any) -> dict[str, Any]: ...
    def delete_object(self, **kwargs: Any) -> dict[str, Any]: ...
    def list_object_versions(self, **kwargs: Any) -> dict[str, Any]: ...


class S3Storage:
    def __init__(self, cache: LocalStorage, bucket: str, client: S3Client) -> None:
        self.cache, self.bucket, self.client = cache, bucket, client

    def _versioned(self) -> None:
        if self.client.get_bucket_versioning(Bucket=self.bucket).get("Status") != "Enabled":
            raise StorageUnavailableError("Original storage must have versioning enabled.")

    @staticmethod
    def _check_version(response: dict[str, Any]) -> None:
        if response.get("VersionId") in (None, "", "null"):
            raise StorageUnavailableError("Original storage did not confirm a durable version.")

    def store(self, tenant_id: str, sha256: str, ext: str, src: Path) -> None:
        key = object_key(tenant_id, sha256, ext)
        try:
            if file_digest(src) != sha256:
                raise StorageUnavailableError("Document integrity verification failed.")
            self._versioned()
            with src.open("rb") as body:
                result = self.client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=body,
                    ChecksumSHA256=base64.b64encode(bytes.fromhex(sha256)).decode("ascii"),
                    Metadata={"sha256": sha256},
                )
            self._check_version(result)
            self.cache.store(tenant_id, sha256, ext, src)
        except (BotoCoreError, ClientError, OSError):
            raise StorageUnavailableError(
                "Could not confirm the independent original copy."
            ) from None

    def path_for(self, tenant_id: str, sha256: str, ext: str) -> Path:
        path = self.cache.path_for(tenant_id, sha256, ext)
        temporary: Path | None = None
        try:
            if path.is_file() and file_digest(path) == sha256:
                return path
            response = self.client.get_object(
                Bucket=self.bucket, Key=object_key(tenant_id, sha256, ext)
            )
            self._check_version(response)
            durable_directory(path.parent)
            body = response["Body"]
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as out:
                    temporary = Path(out.name)
                    while chunk := body.read(1024 * 1024):
                        out.write(chunk)
            finally:
                body.close()
            # LocalStorage validates SHA before atomic cache publication.
            self.cache.store(tenant_id, sha256, ext, temporary)
            return path
        except (BotoCoreError, ClientError, OSError):
            raise StorageUnavailableError(
                "Could not retrieve a verified original document."
            ) from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _confirm_delete_marker(self, key: str, version_id: str) -> bool:
        """OCI omits DeleteMarker on deletion; verify its exact latest version separately."""
        cursor: dict[str, str] = {}
        # A broken or excessively long listing must fail closed, never loop indefinitely.
        for _ in range(10):
            page = self.client.list_object_versions(
                Bucket=self.bucket, Prefix=key, MaxKeys=1000, **cursor
            )
            if any(
                marker.get("Key") == key
                and marker.get("VersionId") == version_id
                and marker.get("IsLatest") is True
                for marker in page.get("DeleteMarkers", [])
            ):
                return True
            if page.get("IsTruncated") is not True:
                return False
            next_key, next_version = page.get("NextKeyMarker"), page.get("NextVersionIdMarker")
            if not isinstance(next_key, str) or not next_key:
                return False
            if not isinstance(next_version, str) or not next_version:
                return False
            following = {"KeyMarker": next_key, "VersionIdMarker": next_version}
            if following == cursor:
                return False
            cursor = following
        return False

    def delete(self, tenant_id: str, sha256: str, ext: str) -> None:
        try:
            key = object_key(tenant_id, sha256, ext)
            self._versioned()
            result = self.client.delete_object(Bucket=self.bucket, Key=key)
            self._check_version(result)
            if result.get("DeleteMarker") is not True and (
                "DeleteMarker" in result
                or not self._confirm_delete_marker(key, result["VersionId"])
            ):
                raise StorageUnavailableError("Original storage did not confirm a delete marker.")
            # Never delete a VersionId: old versions remain available for recovery.
            self.cache.delete(tenant_id, sha256, ext)
        except (BotoCoreError, ClientError, OSError):
            raise StorageUnavailableError("Could not confirm document removal.") from None

    def verify_remote(self, tenant_id: str, sha256: str, ext: str) -> None:
        """Release/restore proof bypasses the local cache and checks independent bytes."""
        try:
            result = self.client.get_object(
                Bucket=self.bucket, Key=object_key(tenant_id, sha256, ext)
            )
            self._check_version(result)
            body, digest = result["Body"], hashlib.sha256()
            try:
                while chunk := body.read(1024 * 1024):
                    digest.update(chunk)
            finally:
                body.close()
            if digest.hexdigest() != sha256:
                raise StorageUnavailableError("Independent original failed integrity verification.")
        except (BotoCoreError, ClientError, OSError):
            raise StorageUnavailableError("Could not verify the independent original.") from None


def create_s3_storage(settings: Settings, cache: LocalStorage) -> S3Storage:
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        config=Config(connect_timeout=5, read_timeout=30, retries={"total_max_attempts": 2}),
    )
    assert settings.s3_bucket is not None  # validated at startup
    return S3Storage(cache, settings.s3_bucket, cast(S3Client, client))
