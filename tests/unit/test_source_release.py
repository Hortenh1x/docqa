"""Public source releases contain reviewed build inputs, never workspace data."""

import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

BUILDER = Path(__file__).resolve().parents[2] / "scripts/build_source.py"


@pytest.fixture
def source_tree(tmp_path):
    root = tmp_path / "workspace"
    files = {
        "LICENSE": "test license\n",
        "README.md": "Build instructions\n",
        "app/main.py": "print('source')\n",
        "ui/src/app/page.tsx": "export default function Page() {}\n",
        "ui/package-lock.json": "{}\n",
        "ui/public/licenses/font-OFL.txt": "third-party notice\n",
        ".env.example": "OPENAI_API_KEY=\n",
        "scripts/dev.sh": "#!/bin/sh\ntrue\n",
    }
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    (root / "scripts/dev.sh").chmod(0o755)
    manifest = root / "scripts/source-files.txt"
    manifest.write_text("\n".join(sorted([*files, "scripts/source-files.txt"])) + "\n")
    return root


def run_builder(root, output):
    return subprocess.run(
        [sys.executable, str(BUILDER), "--root", str(root), "--output", str(output)],
        text=True,
        capture_output=True,
    )


def test_release_is_deterministic_and_contains_exact_build_inputs(source_tree, tmp_path):
    for private in (
        ".env",
        "data/private.txt",
        "audit/notes.md",
        "corpus/external.md",
        "ui/node_modules/private.txt",
        "ui/public/source/old.tar.gz",
    ):
        path = source_tree / private
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("must not be published")
    outputs = [tmp_path / "release-a", tmp_path / "release-b"]
    for output in outputs:
        result = run_builder(source_tree, output)
        assert result.returncode == 0, result.stderr
    offer = json.loads((outputs[0] / "ui/public/source/manifest.json").read_text())
    archive = outputs[0] / "ui/public/source" / offer["archive"]
    assert archive.read_bytes() == (outputs[1] / "ui/public/source" / offer["archive"]).read_bytes()
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == offer["sha256"]
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        names = {item.name.removeprefix("docqa/") for item in members}
        expected = set((source_tree / "scripts/source-files.txt").read_text().splitlines())
        assert names == expected | {"SOURCE-MANIFEST.json"}
        assert all(item.isfile() and item.mtime == item.uid == item.gid == 0 for item in members)
        assert bundle.getmember("docqa/scripts/dev.sh").mode == 0o755
        for name in expected:
            assert bundle.extractfile("docqa/" + name).read() == (source_tree / name).read_bytes()
            assert (outputs[0] / name).read_bytes() == (source_tree / name).read_bytes()


@pytest.mark.parametrize("link_directory", [False, True])
def test_release_rejects_symlink_files_and_parents(source_tree, tmp_path, link_directory):
    if link_directory:
        (source_tree / "app").rename(tmp_path / "outside-app")
        (source_tree / "app").symlink_to(tmp_path / "outside-app", target_is_directory=True)
    else:
        (source_tree / "app/main.py").unlink()
        (source_tree / "app/main.py").symlink_to(source_tree / "README.md")
    result = run_builder(source_tree, tmp_path / "release")
    assert result.returncode != 0
    assert "symlink" in result.stderr.lower()
    assert not (tmp_path / "release").exists()


@pytest.mark.parametrize(
    "private",
    [
        "../outside.py",
        "/etc/passwd",
        ".env",
        "ui/.env.local",
        "data/file.py",
        "audit/check.py",
        "corpus/text.md",
    ],
)
def test_manifest_cannot_allow_private_or_escaping_paths(source_tree, tmp_path, private):
    with (source_tree / "scripts/source-files.txt").open("a") as manifest:
        manifest.write(private + "\n")
    result = run_builder(source_tree, tmp_path / "release")
    assert result.returncode != 0
    assert "Disallowed source path" in result.stderr


def test_new_runtime_source_requires_allowlist_review(source_tree, tmp_path):
    (source_tree / "app/new_feature.py").write_text("new = True\n")
    result = run_builder(source_tree, tmp_path / "release")
    assert result.returncode != 0
    assert "app/new_feature.py" in result.stderr
    assert "allowlist" in result.stderr


def test_existing_release_is_never_overwritten(source_tree, tmp_path):
    output = tmp_path / "release"
    output.mkdir()
    (output / "keep.txt").write_text("preserve")
    result = run_builder(source_tree, output)
    assert result.returncode != 0
    assert (output / "keep.txt").read_text() == "preserve"


def test_manifest_cannot_publish_a_private_key(source_tree, tmp_path):
    (source_tree / "app/main.py").write_text("-----BEGIN PRIVATE KEY-----\nsecret")
    result = run_builder(source_tree, tmp_path / "release")
    assert result.returncode != 0
    assert "secret" in result.stderr.lower()


def test_environment_example_cannot_accidentally_publish_credentials(source_tree, tmp_path):
    (source_tree / ".env.example").write_text("SMTP_PASSWORD=accidentally-filled\n")
    result = run_builder(source_tree, tmp_path / "release")
    assert result.returncode != 0
    assert "secret" in result.stderr.lower()


def test_new_asset_type_also_requires_review(source_tree, tmp_path):
    (source_tree / "ui/public/photo.jpeg").write_bytes(b"asset")
    result = run_builder(source_tree, tmp_path / "release")
    assert result.returncode != 0
    assert "allowlist" in result.stderr
