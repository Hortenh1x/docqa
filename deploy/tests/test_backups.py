"""Backup bundles fail closed on incomplete or modified artifacts."""

import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest


def backup_module():
    path = Path(__file__).parents[1] / "scripts/backup.py"
    assert path.exists(), "A verified DB plus files backup command is required"
    spec = importlib.util.spec_from_file_location("docqa_backup", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backup_verification_rejects_incomplete_and_modified_bundles(tmp_path):
    module = backup_module()
    with pytest.raises((ValueError, FileNotFoundError)):
        module.verify_bundle(tmp_path)
    for name in ("database.dump", "files.tar.gz"):
        (tmp_path / name).write_bytes(b"synthetic")
    manifest = {
        "format": 1,
        "files": {
            name: module.checksum(tmp_path / name) for name in ("database.dump", "files.tar.gz")
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    assert module.verify_bundle(tmp_path) == manifest
    (tmp_path / "database.dump").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        module.verify_bundle(tmp_path)


def test_project_lock_rejects_overlapping_backups(tmp_path, monkeypatch):
    module = backup_module()
    monkeypatch.setattr(module.tempfile, "gettempdir", lambda: str(tmp_path))
    with (
        module.project_lock("synthetic"),
        pytest.raises(RuntimeError, match="already running"),
        module.project_lock("synthetic"),
    ):
        pytest.fail("Overlapping backups must not both control the same writers")
    with module.project_lock("synthetic"):
        pass


def test_failed_dump_resumes_original_writers_and_never_publishes_bundle(tmp_path, monkeypatch):
    module = backup_module()
    monkeypatch.setattr(module.tempfile, "gettempdir", lambda: str(tmp_path))

    class FailingCompose:
        def __init__(self):
            self.stopped = False
            self.resumed = None

        def call(self, *args, **kwargs):
            output = b""
            if args[0] == "config":
                output = json.dumps(
                    {"name": "synthetic", "services": {"db": {"image": "synthetic"}}}
                ).encode()
            elif args[:2] == ("ps", "--status"):
                output = b"db redis" if self.stopped else b"db redis api worker beat"
            elif args[0] == "stop":
                self.stopped = True
            elif args[0] == "start":
                self.resumed = args[1:]
            elif "pg_dump" in args:
                raise RuntimeError("Synthetic dump failure")
            return SimpleNamespace(stdout=output)

        def sql(self, query):
            if "pg_stat_activity" in query:
                return "0"
            if "version_num" in query:
                return "0008"
            if query == module.COUNTS_SQL:
                return json.dumps(dict.fromkeys(module.TABLES, 0))
            return ""

    compose = FailingCompose()
    with pytest.raises(RuntimeError, match="Synthetic dump failure"):
        module.backup(compose, tmp_path / "bundle")
    assert compose.resumed == ("beat", "api", "worker")
    assert not (tmp_path / "bundle").exists()
    assert not list(tmp_path.glob("*.incomplete-*/manifest.json"))


@pytest.mark.parametrize("name", ["../escape.txt", "/absolute.txt"])
def test_archive_paths_fail_closed(tmp_path, name):
    module = backup_module()
    archive = tmp_path / "files.tar.gz"
    with tarfile.open(archive, "w:gz") as files:
        entry = tarfile.TarInfo(name)
        entry.size = 1
        files.addfile(entry, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="Unsafe"):
        module.verify_originals(archive, [])


def test_originals_verify_forward_only_archive_with_reversed_references():
    module = backup_module()
    archive = io.BytesIO()
    references = []
    with tarfile.open(fileobj=archive, mode="w:gz") as files:
        for index in range(20):
            data = (f"document {index} " * 1000).encode()
            digest = hashlib.sha256(data).hexdigest()
            references.append(("tenant", digest, "text/plain"))
            entry = tarfile.TarInfo(f"files/tenant/{digest}.txt")
            entry.size = len(data)
            files.addfile(entry, io.BytesIO(data))

    class ForwardOnly(io.BytesIO):
        def seek(self, *args):
            raise AssertionError("Verification must not reread compressed archive data")

    module.verify_originals(ForwardOnly(archive.getvalue()), references[::-1])
    with pytest.raises(ValueError, match="Missing original"):
        module.verify_originals(
            ForwardOnly(archive.getvalue()), [("tenant", "f" * 64, "text/plain")]
        )


@pytest.mark.parametrize("duplicate", [False, True])
def test_originals_stream_rejects_corruption_and_duplicate_members(duplicate):
    module = backup_module()
    data = b"expected original"
    digest = hashlib.sha256(data).hexdigest()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as files:
        for content in [data, b"replacement"] if duplicate else [b"corrupted"]:
            entry = tarfile.TarInfo(f"files/tenant/{digest}.txt")
            entry.size = len(content)
            files.addfile(entry, io.BytesIO(content))
    archive.seek(0)
    with pytest.raises(ValueError, match="duplicate" if duplicate else "hash mismatch"):
        module.verify_originals(archive, [("tenant", digest, "text/plain")])


def test_restore_cleanup_failures_are_reported_after_all_removals_are_attempted(monkeypatch):
    module = backup_module()
    calls = []

    def failing_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1, stderr=b"Docker unavailable")

    monkeypatch.setattr(module, "run", failing_run)
    with pytest.raises(RuntimeError, match="cleanup failed"):
        module.cleanup_restore("synthetic-container", ["synthetic-db", "synthetic-files"])
    assert len(calls) == 3


class SuccessfulCompose:
    """Run the backup filesystem path without Docker or an external database."""

    def __init__(self, module):
        self.module = module
        self.stopped = False
        self.resumed = None

    def call(self, *args, **kwargs):
        output = b""
        if args[0] == "config":
            output = json.dumps(
                {"name": "synthetic", "services": {"db": {"image": "synthetic"}}}
            ).encode()
        elif args[:2] == ("ps", "--status"):
            output = b"db redis" if self.stopped else b"db redis api worker beat"
        elif args[0] == "stop":
            self.stopped = True
        elif args[0] == "start":
            self.resumed = args[1:]
        elif "pg_dump" in args:
            kwargs["stdout"].write(b"synthetic database dump")
        elif "-czf" in args:
            with tarfile.open(fileobj=kwargs["stdout"], mode="w:gz"):
                pass
        return SimpleNamespace(stdout=output)

    def sql(self, query):
        if "pg_stat_activity" in query:
            return "0"
        if "version_num" in query:
            return "0009"
        if query == self.module.COUNTS_SQL:
            return json.dumps(dict.fromkeys(self.module.TABLES, 0))
        return ""


def observe_syncs(module, monkeypatch, events):
    """Observe the actual open filesystem descriptor at each durability barrier."""
    real_sync = module.os.fsync

    def sync(descriptor):
        path = Path(f"/proc/self/fd/{descriptor}").resolve()
        real_sync(descriptor)
        events.append(("sync", path))

    monkeypatch.setattr(module.os, "fsync", sync)


def test_backup_persists_artifacts_and_all_new_entries_before_success(
    tmp_path, monkeypatch, capsys
):
    module = backup_module()
    compose = SuccessfulCompose(module)
    monkeypatch.setattr(module.tempfile, "gettempdir", lambda: str(tmp_path))
    destination = tmp_path / "new-parent" / "backups" / "bundle"
    events = []
    observe_syncs(module, monkeypatch, events)
    real_rename = Path.rename

    def rename(source, target):
        events.append(("rename", source))
        return real_rename(source, target)

    monkeypatch.setattr(Path, "rename", rename)

    module.backup(compose, destination)

    publication = next(index for index, event in enumerate(events) if event[0] == "rename")
    staging = events[publication][1]
    before = events[:publication]
    for name in (*module.ARTIFACTS, "manifest.json"):
        assert ("sync", staging / name) in before, f"{name} must be durable before publication"
    assert ("sync", staging) in before
    assert before.index(("sync", staging)) > max(
        before.index(("sync", staging / name)) for name in (*module.ARTIFACTS, "manifest.json")
    )
    for parent in (tmp_path, destination.parent.parent, destination.parent):
        assert ("sync", parent) in before, f"New directory entry in {parent} was not durable"
    assert events[publication + 1 :] == [("sync", destination.parent)]
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    assert module.verify_bundle(destination)["document_references"] == 0
    assert compose.resumed == ("beat", "api", "worker")


@pytest.mark.parametrize("failure", ["ancestor", "artifact", "manifest", "staging", "publish"])
def test_backup_fsync_failures_never_report_success(tmp_path, monkeypatch, capsys, failure):
    module = backup_module()
    compose = SuccessfulCompose(module)
    monkeypatch.setattr(module.tempfile, "gettempdir", lambda: str(tmp_path))
    destination = tmp_path / "new-parent" / "backups" / "bundle"
    real_sync = module.os.fsync

    def sync(descriptor):
        path = Path(f"/proc/self/fd/{descriptor}").resolve()
        fail = (
            failure == "ancestor"
            and path == tmp_path
            or failure == "artifact"
            and path.name == "database.dump"
            or failure == "manifest"
            and path.name == "manifest.json"
            or failure == "staging"
            and ".incomplete-" in path.name
            or failure == "publish"
            and path == destination.parent
            and destination.exists()
        )
        if fail:
            raise OSError("Synthetic fsync failure")
        real_sync(descriptor)

    monkeypatch.setattr(module.os, "fsync", sync)

    with pytest.raises(OSError, match="Synthetic fsync failure"):
        module.backup(compose, destination)

    assert '"status": "ok"' not in capsys.readouterr().out
    if failure != "publish":
        assert not destination.exists()
    if failure != "ancestor":
        assert compose.resumed == ("beat", "api", "worker")


def test_backup_retry_resyncs_existing_ancestor_after_failed_creation(tmp_path, monkeypatch):
    module = backup_module()
    destination = tmp_path / "new-parent" / "backups" / "bundle"
    monkeypatch.setattr(module.tempfile, "gettempdir", lambda: str(tmp_path))
    real_sync = module.sync_directory
    synced = []
    fail_once = True

    def sync(path):
        nonlocal fail_once
        if path == tmp_path and fail_once:
            fail_once = False
            raise OSError("Synthetic fsync failure")
        real_sync(path)
        synced.append(path)

    monkeypatch.setattr(module, "sync_directory", sync)
    with pytest.raises(OSError):
        module.backup(SuccessfulCompose(module), destination)
    module.backup(SuccessfulCompose(module), destination)
    assert tmp_path in synced
    assert module.verify_bundle(destination)["document_references"] == 0
