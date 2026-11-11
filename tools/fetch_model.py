"""Explicit, hash-checked source model download for developers/CI only."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / 'models/manifest.json').read_text(encoding='utf-8'))
    destination = ROOT / 'models' / manifest['source']
    expected = manifest['source_sha256']
    if destination.is_file():
        with destination.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise SystemExit('Existing model hash mismatch; refusing to overwrite it.')
        print('Existing pinned model verified.')
        return
    temporary = destination.with_suffix('.pt.download')
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(manifest['source_url'], temporary)
        with temporary.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise RuntimeError('Downloaded model SHA-256 mismatch.')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print('Pinned model downloaded and verified.')


if __name__ == '__main__':
    main()
