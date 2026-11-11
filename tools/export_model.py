"""Export the pinned local checkpoint, without fetching or training another model."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--extra-site', type=Path)
    args = parser.parse_args()
    if args.extra_site:
        import site
        site.addsitedir(str(args.extra_site))
    from ultralytics import YOLO
    model = ROOT / 'models/yolo26s-pose.pt'
    if not model.is_file():
        raise SystemExit('Missing local model: ' + str(model))
    output = YOLO(str(model), task='pose').export(format='onnx', imgsz=640, batch=1, dynamic=False,
                                               simplify=False, opset=18, device='cpu')
    path = Path(output)
    import onnx
    exported = onnx.load(str(path))
    onnx.checker.check_model(exported)
    def sha(p):
        with p.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    manifest = {'source': model.name, 'source_sha256': sha(model), 'onnx': path.name,
                'onnx_sha256': sha(path), 'input': [1, 3, 640, 640], 'precision': 'FP32',
                'opset': 18, 'candidate_only': True,
                'source_url': 'https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26s-pose.pt',
                'license': 'AGPL-3.0; conversion does not change source license'}
    (ROOT / 'models/manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
