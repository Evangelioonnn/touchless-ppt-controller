"""Lightweight entry point: errors and instance checks precede ML imports."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time

from app_paths import VERSION, user_data_dir
from app_settings import Settings, SettingsStore
from diagnostics import Protocol, StartupTrace, configure_logging


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--protocol', action='store_true', help='Local launcher JSON over standard streams')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--backend', choices=('torch', 'onnx'))
    parser.add_argument('--default-backend', choices=('torch', 'onnx'), help='Launcher default, only if no valid saved settings')
    parser.add_argument('--device', choices=('auto', 'cpu', 'cuda'))
    parser.add_argument('--self-check', action='store_true', help='Check dependencies and model; never open a camera')
    parser.add_argument('--observe-only', action='store_true', help='Diagnostics: never send PowerPoint commands')
    parser.add_argument('--duration', type=float, default=0, help='Diagnostic auto-stop seconds; 0 is unlimited')
    parser.add_argument('--metrics', type=Path, help='Optional local resource report, with no image data')
    parser.add_argument('--native-preview-map', help='Private local-session channel for the native preview')
    args = parser.parse_args()
    protocol = Protocol(args.protocol)
    if args.protocol:
        # Keep library output out of the JSON channel.
        sys.stdout = sys.stderr
    logger = configure_logging()
    trace = StartupTrace(logger, protocol)
    trace.mark('bootstrap')
    instance = None
    try:
        extra_site = os.environ.get('TOUCHLESS_PPT_EXTRA_SITE')
        if not extra_site and not getattr(sys, 'frozen', False):
            local_runtime = Path(__file__).resolve().parent / '.venv-release/Lib/site-packages'
            if local_runtime.is_dir():
                extra_site = str(local_runtime)
        if extra_site and not getattr(sys, 'frozen', False):
            import site
            site.addsitedir(extra_site)
        from windows_support import SingleInstance, activate_existing
        if not args.self_check:
            instance = SingleInstance()
            if instance.already_running:
                activate_existing()
                protocol.send('already_running')
                return 0
        store = SettingsStore()
        settings = store.load()
        if args.default_backend and (not store.path.is_file() or store.warnings):
            settings.backend = args.default_backend
        if args.backend:
            settings.backend = args.backend
        if args.device:
            settings.device = args.device
        for warning in store.warnings:
            logger.warning(warning)
            protocol.send('warning', message=warning)
        if args.self_check:
            import importlib.util
            from controller_config import MODEL_PATH, ONNX_MODEL_PATH
            import cv2
            import numpy
            from pose_backends import OnnxBackend, TorchBackend
            model = ONNX_MODEL_PATH if settings.backend == 'onnx' else MODEL_PATH
            module = 'onnxruntime' if settings.backend == 'onnx' else 'torch'
            backend = (OnnxBackend(model, settings.device) if settings.backend == 'onnx' else TorchBackend(model, settings.device))
            prediction = backend.predict(numpy.zeros((720, 1280, 3), numpy.uint8), time.perf_counter())
            result = {'version': VERSION, 'backend': settings.backend, 'model_exists': model.is_file(),
                      'runtime_installed': importlib.util.find_spec(module) is not None,
                      'opencv': cv2.__version__, 'numpy': numpy.__version__,
                      'torch_imported': 'torch' in sys.modules, 'data_dir': str(user_data_dir()),
                      'inference_ok': True, 'frozen': bool(getattr(sys, 'frozen', False)),
                      'numpy_location': numpy.__file__, 'cv2_location': cv2.__file__, 'device': backend.name}
            print(json.dumps(result), file=protocol.stream or sys.stderr)
            return 0 if result['model_exists'] and result['runtime_installed'] else 2
        trace.mark('resources_checked')
        from controller_runtime import run
        native_preview = None
        if args.native_preview_map:
            if not args.protocol:
                raise ValueError('Native preview requires the local launcher protocol.')
            from preview_transport import FramePublisher
            native_preview = FramePublisher(args.native_preview_map)
        return run(settings, store, protocol, trace, logger, headless=args.headless or native_preview is not None,
                   observe_only=args.observe_only, duration=args.duration, metrics_path=args.metrics,
                   native_preview=native_preview)
    except Exception as error:
        logger.exception('Controller failed')
        protocol.send('error', message=str(error), log_dir=str(user_data_dir() / 'logs'))
        if args.self_check:
            print(json.dumps({'ok': False, 'error': str(error)}), file=protocol.stream or sys.stderr)
            return 1
        if not args.protocol:
            from windows_support import error_dialog
            error_dialog(str(error) + '\n\nLogs: ' + str(user_data_dir() / 'logs'))
        return 1
    finally:
        trace.save()
        if instance is not None:
            instance.close()


if __name__ == '__main__':
    raise SystemExit(main())
