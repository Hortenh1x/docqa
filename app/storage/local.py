"""Local-disk storage."""

import shutil
from pathlib import Path

from app.config import get_settings


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, tenant_id: str, sha256: str, ext: str) -> Path:
        return self.root / tenant_id / f"{sha256}{ext}"

    def store(self, tenant_id: str, sha256: str, ext: str, src: Path) -> None:
        dest = self.path_for(tenant_id, sha256, ext)
        if dest.exists():
            # same content already stored (content-addressed) — keep it, drop the temp copy
            src.unlink(missing_ok=True)
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dest)

    def delete(self, tenant_id: str, sha256: str, ext: str) -> None:
        self.path_for(tenant_id, sha256, ext).unlink(missing_ok=True)


def get_storage() -> LocalStorage:
    return LocalStorage(get_settings().storage_dir)
