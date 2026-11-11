"""Dependency-free resource and per-user path resolution."""
from __future__ import annotations

import os
from pathlib import Path
import sys

VERSION = '0.2.0-beta.3'
CODE_ROOT = Path(__file__).resolve().parent
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else CODE_ROOT


def resource_path(name: str) -> Path:
    bundle = Path(getattr(sys, '_MEIPASS', CODE_ROOT))
    for root in (APP_ROOT, bundle, CODE_ROOT):
        candidate = root / name
        if candidate.is_file():
            return candidate
    return APP_ROOT / name


def user_data_dir() -> Path:
    override = os.environ.get('TOUCHLESS_PPT_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share')))
    return base / 'TouchlessPPTController'

