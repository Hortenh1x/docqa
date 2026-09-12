#!/usr/bin/env python3
"""Prepare a reviewed, deterministic source archive and matching release build tree.

Only paths explicitly listed in source-files.txt may be published. Git state is
irrelevant: the bytes in the working tree are the bytes used in both outputs.
No dependencies beyond Python's standard library are required.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import stat
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT_FILES = {
    "LICENSE",
    "NOTICE",
    "README.md",
    "docs.md",
    "Dockerfile",
    ".dockerignore",
    ".env.example",
    ".gitignore",
    ".python-version",
    ".pre-commit-config.yaml",
    "pyproject.toml",
    "uv.lock",
    "alembic.ini",
    "docker-compose.yml",
    "docker-compose.prod.yml",
}
SOURCE_SUFFIXES = {
    "app": {".py"},
    "alembic": {".py", ".mako"},
    "scripts": {".py", ".sh", ".txt"},
    "tests": {".py", ".txt", ".md"},
    "eval": {".py"},
    "docs": {".md", ".gif", ".png", ".svg"},
    "deploy": {".py", ".sh", ".sql", ".yml", ".md"},
    ".github": {".yml"},
    "ui": {
        ".ts",
        ".tsx",
        ".js",
        ".mjs",
        ".cjs",
        ".json",
        ".css",
        ".svg",
        ".png",
        ".ico",
        ".woff2",
        ".txt",
        ".md",
    },
}
SPECIAL_FILES = {
    "alembic/README",
    "deploy/Caddyfile",
    "ui/Dockerfile",
    "ui/.dockerignore",
    "ui/.gitignore",
    "ui/.env.example",
}
EXCLUDED_PARTS = {
    "node_modules",
    "__pycache__",
    "data",
    "backups",
    "audit",
    "plans",
    "corpus",
    "graphify-out",
    ".release",
    ".next",
    "out",
    "dist",
}
SECRET_PATTERN = re.compile(
    rb"(?m)^-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}"
)


def allowed_path(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or str(path) != name or "\\" in name:
        return False
    if name in ROOT_FILES or name in SPECIAL_FILES:
        return True
    if any(
        part in EXCLUDED_PARTS or (part.startswith(".") and part != ".github")
        for part in path.parts
    ):
        return False
    if path.parts[:3] == ("ui", "public", "source"):
        return False
    return len(path.parts) > 1 and path.suffix in SOURCE_SUFFIXES.get(path.parts[0], set())


def read_regular(root: Path, name: str) -> tuple[bytes, int]:
    path = root
    for part in PurePosixPath(name).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"Refusing source symlink: {name}")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"Not a regular source file: {name}")
    data = path.read_bytes()
    if SECRET_PATTERN.search(data):
        raise ValueError(f"Possible secret in reviewed source: {name}")
    if path.name == ".env.example":
        for line in data.decode().splitlines():
            key, separator, value = line.partition("=")
            if not key.lstrip().startswith("#") and separator:
                value = value.split("#", 1)[0].strip().strip("\"'")
                if value and key.strip().endswith(("_KEY", "_KEY_ID", "_SECRET", "_PASSWORD")):
                    raise ValueError(f"Possible secret in environment example: {name} ({key})")
    return data, 0o755 if info.st_mode & 0o111 else 0o644


def collect_source(root: Path) -> dict[str, tuple[bytes, int]]:
    manifest, _ = read_regular(root, "scripts/source-files.txt")
    names = [line for line in manifest.decode().splitlines() if line and not line.startswith("#")]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate source allowlist entry")
    for name in names:
        if not allowed_path(name):
            raise ValueError(f"Disallowed source path: {name}")
    # New build inputs must not silently disappear from the corresponding source.
    # os.walk never follows directory symlinks; read_regular rejects listed links.
    for directory in ("app", "alembic", "ui/src", "ui/public", "ui/scripts"):
        for parent, children, files in os.walk(root / directory, followlinks=False):
            children[:] = [
                name
                for name in children
                if name not in EXCLUDED_PARTS
                and not name.startswith(".")
                and (Path(parent) / name) != root / "ui/public/source"
            ]
            for filename in files:
                name = (Path(parent) / filename).relative_to(root).as_posix()
                if name not in names:
                    raise ValueError(f"Review and add new source to the allowlist: {name}")
    return {name: read_regular(root, name) for name in sorted(names)}


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def build_release(root: Path, output: Path) -> dict[str, object]:
    if output.exists() or output.is_symlink():
        raise ValueError("Release output already exists; choose a new directory")
    files = collect_source(root)
    inventory = {
        name: {"sha256": hashlib.sha256(data).hexdigest(), "mode": mode}
        for name, (data, mode) in files.items()
    }
    manifest = json_bytes({"format": 1, "files": inventory})
    release_id = hashlib.sha256(manifest).hexdigest()
    archive_buffer = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=archive_buffer, mode="wb", filename="", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        contents = {**files, "SOURCE-MANIFEST.json": (manifest, 0o644)}
        for name, (data, mode) in sorted(contents.items()):
            entry = tarfile.TarInfo("docqa/" + name)
            entry.size, entry.mode, entry.mtime = len(data), mode, 0
            archive.addfile(entry, io.BytesIO(data))
    archive_bytes = archive_buffer.getvalue()
    offer = {
        "format": 1,
        "release": release_id,
        "archive": f"docqa-source-{release_id}.tar.gz",
        "sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "files": inventory,
    }
    # Reject edits during collection rather than publishing a mixed snapshot.
    if collect_source(root) != files:
        raise ValueError("Source changed during packaging; retry with a quiet working tree")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".docqa-source-", dir=output.parent) as temporary:
        prepared = Path(temporary) / "release"
        for name, (data, mode) in contents.items():
            target = prepared / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(mode)
        public = prepared / "ui/public/source"
        public.mkdir(parents=True)
        (public / str(offer["archive"])).write_bytes(archive_bytes)
        (public / "manifest.json").write_bytes(json_bytes(offer))
        (public / "LICENSE.txt").write_bytes(files["LICENSE"][0])
        # Rename only into an absent destination; never update a previous release.
        if output.exists() or output.is_symlink():
            raise ValueError("Release output already exists")
        prepared.rename(output)
    return offer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        offer = build_release(args.root.resolve(), args.output.absolute())
    except (ValueError, OSError) as error:
        parser.exit(1, f"Source release failed: {error}\n")
    print(f"Prepared {args.output}: {offer['release']}")
    print(f"Archive SHA-256: {offer['sha256']}")


if __name__ == "__main__":
    main()
