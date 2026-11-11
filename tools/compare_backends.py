"""Compare ONNX decoding against the checkpoint with identical square preprocessing.

Bundled example-image augmentations are a decoder check, NOT a full real-gesture
acceptance dataset. The report deliberately leaves the promotion gate pending.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--extra-site', type=Path)
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--images', type=Path)
    args = parser.parse_args()
    if args.extra_site:
        import site
        site.addsitedir(str(args.extra_site))
    output = ROOT / 'validation/inference-comparison'
    output.mkdir(parents=True, exist_ok=True)
    os.environ['YOLO_CONFIG_DIR'] = str(output / 'ultralytics-config')
    import cv2
    import numpy as np
    import ultralytics
    from ultralytics import YOLO
    from pose_backends import OnnxBackend
    from person_tracker import overlap
    from gesture_engine import detect_pose
    from controller_config import MODEL_PATH, ONNX_MODEL_PATH
    source = args.images if args.images else Path(ultralytics.__file__).parent / 'assets'
    paths = sorted(p for p in source.iterdir() if p.suffix.lower() in ('.jpg', '.png', '.jpeg'))
    if not paths:
        raise SystemExit('No images available')
    network = YOLO(str(MODEL_PATH), task='pose')
    onnx = OnnxBackend(ONNX_MODEL_PATH, 'cpu')
    errors, frames = [], []
    pose_mismatches = 0
    for index in range(args.count):
        path = paths[index % len(paths)]
        image = cv2.imread(str(path))
        if image is None:
            continue
        # Deterministic variations: no personal camera images or screenshots.
        factor = .7 + .1 * (index % 6)
        image = cv2.convertScaleAbs(image, alpha=factor)
        if index % 3 == 0:
            image = cv2.flip(image, 1)
        if index % 4 == 0:
            image = image[:int(image.shape[0] * .7)].copy()
        if index % 5 == 0:
            h, w = image.shape[:2]
            image = cv2.warpAffine(image, cv2.getRotationMatrix2D((w / 2, h / 2), (index % 9) - 4, 1), (w, h), borderValue=(114,114,114))
        before = time.perf_counter()
        reference = network.predict(image, imgsz=640, conf=.42, device='cpu', rect=False, verbose=False)[0]
        torch_s = time.perf_counter() - before
        before = time.perf_counter()
        actual = onnx.predict(image, before)
        onnx_s = time.perf_counter() - before
        boxes = reference.boxes.xyxy.cpu().numpy() if reference.boxes is not None else []
        kp = reference.keypoints.xy.cpu().numpy() if reference.keypoints is not None else []
        confidence = reference.keypoints.conf.cpu().numpy() if reference.keypoints is not None else []
        used = set()
        pairs = 0
        for ref_index, box in enumerate(boxes):
            choices = [(overlap(box, person.box), number, person) for number, person in enumerate(actual.people) if number not in used]
            if not choices:
                continue
            iou, number, person = max(choices, key=lambda item: item[0])
            if iou < .5:
                continue
            used.add(number); pairs += 1
            mask = (confidence[ref_index] >= .4) & (person.scores >= .4)
            indices = np.array([5,6,7,8,9,10])
            indices = indices[mask[indices]]
            if len(indices):
                distance = np.linalg.norm(kp[ref_index][indices] - person.points[indices], axis=1)
                errors.extend((distance / np.hypot(*image.shape[:2])).tolist())
            if detect_pose(kp[ref_index], confidence[ref_index])[0] != detect_pose(person.points, person.scores)[0]:
                pose_mismatches += 1
        frames.append({'index': index, 'source': path.name, 'torch_people': len(boxes), 'onnx_people': len(actual.people),
                       'matched_people': pairs, 'torch_cpu_s': torch_s, 'onnx_cpu_s': onnx_s})
        if index % 20 == 0:
            print('Compared %d/%d' % (index + 1, args.count), flush=True)
    report = {'dataset': 'user-provided images' if args.images else 'deterministic augmentations of two Ultralytics bundled example images',
              'distinct_source_images': len(paths), 'frames': frames, 'reliable_joint_pairs': len(errors),
              'normalized_keypoint_error_p95': float(np.percentile(errors, 95)) if errors else None,
              'p95_limit': .005, 'pose_label_mismatches': pose_mismatches,
              'torch_cpu_median_s': float(np.median([f['torch_cpu_s'] for f in frames])),
              'onnx_cpu_median_s': float(np.median([f['onnx_cpu_s'] for f in frames])),
              'promotion_approved': False,
              'pending': ['representative seated/occluded real gesture sequences', 'real gesture event replay',
                          'camera and PowerPoint end-to-end acceptance', 'OS cold-start trials']}
    (output / 'comparison.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    summary = {key: value for key, value in report.items() if key != 'frames'}
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
