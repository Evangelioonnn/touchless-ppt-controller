"""Lazy, interchangeable Torch/ONNX inference; model conversion is build-time only."""
from __future__ import annotations

import logging
from pathlib import Path
import time

from pose_types import Person, PoseResult
from controller_config import DETECTION_CONFIDENCE, IMAGE_SIZE


class TorchBackend:
    def __init__(self, model_path: Path, device: str = 'auto', stage=lambda name: None):
        if not model_path.is_file():
            raise FileNotFoundError('Local pose model not found: ' + str(model_path))
        import os
        from app_paths import user_data_dir
        config_directory = user_data_dir() / 'ultralytics'
        config_directory.mkdir(parents=True, exist_ok=True)
        os.environ['YOLO_CONFIG_DIR'] = str(config_directory)
        os.environ['YOLO_OFFLINE'] = 'True'
        os.environ['YOLO_AUTOINSTALL'] = 'False'
        stage('loading_torch')
        import torch
        stage('loading_ultralytics')
        from ultralytics import YOLO
        self.torch = torch
        self.device, self.name = 'cpu', 'CPU'
        if device != 'cpu':
            try:
                if torch.cuda.is_available():
                    self.name = torch.cuda.get_device_name(0)
                    self.device = 0
            except Exception:
                logging.getLogger('touchless').warning('GPU initialization failed; using CPU', exc_info=True)
                self.device, self.name = 'cpu', 'CPU (GPU initialization recovery)'
        self.model = YOLO(str(model_path), task='pose')
        self.fallback_used = False
        if self.device == 0:
            torch.backends.cudnn.benchmark = True
        stage('model_loaded')

    def recover_cpu(self) -> bool:
        if self.device == 'cpu' or self.fallback_used:
            return False
        self.fallback_used = True
        self.device = 'cpu'
        self.name = 'CPU (GPU recovery)'
        self.model.to('cpu')
        logging.getLogger('touchless').warning('GPU failed; switched to CPU')
        return True

    def predict(self, image, received_at: float, sequence: int = 0) -> PoseResult:
        import numpy as np
        result = self.model.predict(source=image, imgsz=IMAGE_SIZE, conf=DETECTION_CONFIDENCE,
                                    device=self.device, verbose=False)[0]
        people = []
        if result.keypoints is not None and result.boxes is not None:
            points = result.keypoints.xy.detach().cpu().numpy()
            scores = result.keypoints.conf.detach().cpu().numpy() if result.keypoints.conf is not None else np.ones(points.shape[:2], np.float32)
            boxes = result.boxes.xyxy.detach().cpu().numpy()
            confidences = result.boxes.conf.detach().cpu().numpy()
            people = [Person(box.copy(), pts.copy(), conf.copy(), float(score))
                      for box, pts, conf, score in zip(boxes, points, scores, confidences)]
        return PoseResult(people, received_at, time.perf_counter(), sequence)


def letterbox(image, size: int = IMAGE_SIZE):
    import cv2
    import numpy as np
    height, width = image.shape[:2]
    ratio = min(size / height, size / width)
    resized = (round(width * ratio), round(height * ratio))
    dw, dh = size - resized[0], size - resized[1]
    left, top = round(dw / 2 - .1), round(dh / 2 - .1)
    right, bottom = round(dw / 2 + .1), round(dh / 2 + .1)
    scaled = cv2.resize(image, resized, interpolation=cv2.INTER_LINEAR) if resized != (width, height) else image
    padded = cv2.copyMakeBorder(scaled, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    tensor = np.ascontiguousarray(padded[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
    return tensor, ratio, (left, top)


def decode_pose(output, original_shape, ratio, pad, confidence=DETECTION_CONFIDENCE):
    import cv2
    import numpy as np
    rows = np.asarray(output)
    if rows.ndim == 3:
        rows = rows[0]
    if rows.ndim != 2:
        raise ValueError('Unexpected ONNX output shape: ' + str(rows.shape))
    if rows.shape[0] in (56, 57) and rows.shape[1] not in (56, 57):
        rows = rows.T
    if rows.shape[1] == 57:
        rows = rows[(rows[:, 4] >= confidence) & (rows[:, 5] == 0)]
        boxes, scores, keypoints = rows[:, :4].copy(), rows[:, 4], rows[:, 6:].reshape(-1, 17, 3).copy()
    elif rows.shape[1] == 56:
        rows = rows[rows[:, 4] >= confidence]
        boxes = rows[:, :4].copy()
        boxes[:, :2] -= boxes[:, 2:] / 2
        boxes[:, 2:] += boxes[:, :2]
        scores, keypoints = rows[:, 4], rows[:, 5:].reshape(-1, 17, 3).copy()
        xywh = boxes.copy(); xywh[:, 2:] -= xywh[:, :2]
        keep = np.asarray(cv2.dnn.NMSBoxes(xywh.tolist(), scores.tolist(), confidence, 0.7)).reshape(-1)
        boxes, scores, keypoints = boxes[keep], scores[keep], keypoints[keep]
    else:
        raise ValueError('Expected YOLO26 pose output with 56 or 57 fields, got ' + str(rows.shape))
    h, w = original_shape[:2]
    people = []
    for box, score, kp in zip(boxes, scores, keypoints):
        box[[0, 2]] = np.clip((box[[0, 2]] - pad[0]) / ratio, 0, w)
        box[[1, 3]] = np.clip((box[[1, 3]] - pad[1]) / ratio, 0, h)
        kp[:, 0] = np.clip((kp[:, 0] - pad[0]) / ratio, 0, w)
        kp[:, 1] = np.clip((kp[:, 1] - pad[1]) / ratio, 0, h)
        if np.isfinite(box).all() and np.isfinite(kp).all():
            people.append(Person(box.astype(np.float32), kp[:, :2].astype(np.float32), kp[:, 2].astype(np.float32), float(score)))
    return people


class OnnxBackend:
    def __init__(self, model_path: Path, device: str = 'cpu', stage=lambda name: None):
        if not model_path.is_file():
            raise FileNotFoundError('Local ONNX model not found. Run the build-time export first: ' + str(model_path))
        stage('loading_onnxruntime')
        import onnxruntime as ort
        available = ort.get_available_providers()
        providers = ['CPUExecutionProvider']
        if device != 'cpu':
            for candidate in ('CUDAExecutionProvider', 'DmlExecutionProvider'):
                if candidate in available:
                    providers.insert(0, candidate)
                    break
        options = ort.SessionOptions()
        options.intra_op_num_threads = min(4, __import__('os').cpu_count() or 1)
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.ort, self.options, self.path = ort, options, model_path
        try:
            self.session = ort.InferenceSession(str(model_path), sess_options=options, providers=providers)
        except Exception:
            if providers == ['CPUExecutionProvider']:
                raise
            self.session = ort.InferenceSession(str(model_path), sess_options=options, providers=['CPUExecutionProvider'])
        self.input_name = self.session.get_inputs()[0].name
        self.name = 'ONNX ' + self.session.get_providers()[0].replace('ExecutionProvider', '')
        self.fallback_used = self.session.get_providers()[0] == 'CPUExecutionProvider'
        stage('model_loaded')

    def recover_cpu(self) -> bool:
        if self.fallback_used:
            return False
        self.fallback_used = True
        self.session = self.ort.InferenceSession(str(self.path), sess_options=self.options, providers=['CPUExecutionProvider'])
        self.input_name = self.session.get_inputs()[0].name
        self.name = 'ONNX CPU (GPU recovery)'
        return True

    def predict(self, image, received_at: float, sequence: int = 0) -> PoseResult:
        tensor, ratio, pad = letterbox(image)
        outputs = self.session.run(None, {self.input_name: tensor})
        people = decode_pose(outputs[0], image.shape, ratio, pad)
        return PoseResult(people, received_at, time.perf_counter(), sequence)
