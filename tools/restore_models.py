"""Explicitly restore this release's hash-pinned models; never used at app startup."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_paths import VERSION

MAX_MODEL_BYTES = 128 * 1024 * 1024


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def expected_models(root: Path):
    manifest = json.loads((root / "models/manifest.json").read_text(encoding="utf-8"))
    if manifest["source"] != "yolo26s-pose.pt" or manifest["onnx"] != "yolo26s-pose.onnx":
        raise ValueError("Unexpected model names in manifest")
    return manifest, {manifest["source"]: manifest["source_sha256"], manifest["onnx"]: manifest["onnx_sha256"]}


def check_existing(root: Path, expected: dict[str, str]) -> list[str]:
    missing = []
    for name, expected_hash in expected.items():
        target = root / "models" / name
        if not target.exists():
            missing.append(name)
        elif not target.is_file() or digest(target) != expected_hash:
            raise RuntimeError("Existing model hash mismatch; refusing to overwrite: " + name)
    return missing


def restore_archive(archive: Path, root: Path = ROOT):
    manifest, expected = expected_models(root)
    missing = check_existing(root, expected)
    if not missing:
        return []
    destination = root / "models"
    destination.mkdir(parents=True, exist_ok=True)
    allowed = {"models/manifest.json", *("models/" + name for name in expected)}
    with zipfile.ZipFile(archive) as bundle, tempfile.TemporaryDirectory(prefix=".restore-", dir=destination) as temporary:
        if len(bundle.namelist()) != len(allowed) or set(bundle.namelist()) != allowed:
            raise ValueError("Model archive contains missing, duplicate or unexpected paths")
        if any(info.file_size > MAX_MODEL_BYTES for info in bundle.infolist()):
            raise ValueError("Model archive exceeds size limits")
        if json.loads(bundle.read("models/manifest.json")) != manifest:
            raise ValueError("Archive manifest does not match this source release")
        staged = {}
        for name, expected_hash in expected.items():
            path = Path(temporary) / name
            with bundle.open("models/" + name) as source, path.open("wb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
            if digest(path) != expected_hash:
                raise ValueError("Archive model SHA-256 mismatch: " + name)
            staged[name] = path
        # Validate every file before installing any; re-check before atomic rename.
        missing = check_existing(root, expected)
        for name in missing:
            staged[name].replace(destination / name)
    return missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use an already downloaded release models.zip")
    args = parser.parse_args()
    _, expected = expected_models(ROOT)
    if not check_existing(ROOT, expected):
        print("Both pinned models already exist and passed SHA-256 verification.")
        return
    if args.archive:
        restored = restore_archive(args.archive.resolve())
    else:
        name = f"TouchlessPPTController-v{VERSION}-models.zip"
        url = f"https://github.com/Evangelioonnn/touchless-ppt-controller/releases/download/v{VERSION}/{name}"
        print("Downloading the pinned model backup from release v" + VERSION, flush=True)
        with tempfile.TemporaryDirectory(prefix="touchless-model-download-") as temporary:
            archive = Path(temporary) / name
            request = urllib.request.Request(url, headers={"User-Agent": "TouchlessPPTController-model-restore"})
            with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
                total = 0
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > MAX_MODEL_BYTES * 2:
                        raise ValueError("Download exceeds model archive size limit")
                    output.write(block)
            restored = restore_archive(archive)
    print("Restored and verified: " + ", ".join(restored))


if __name__ == "__main__":
    main()
