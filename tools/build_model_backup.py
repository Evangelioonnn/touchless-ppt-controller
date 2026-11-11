"""Create the corresponding, hash-checked model backup for a source release."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_paths import VERSION


def main():
    manifest = json.loads((ROOT / "models/manifest.json").read_text(encoding="utf-8"))
    files = [(ROOT / "models" / manifest["source"], manifest["source_sha256"]),
             (ROOT / "models" / manifest["onnx"], manifest["onnx_sha256"])]
    for path, expected in files:
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise RuntimeError("Refusing to archive a model with a different hash: " + path.name)
    archive = ROOT / f"dist/TouchlessPPTController-v{VERSION}-models.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in [*(p for p, _ in files), ROOT / "models/manifest.json"]:
            bundle.write(path, path.relative_to(ROOT).as_posix())
    print(archive)


if __name__ == "__main__":
    main()
