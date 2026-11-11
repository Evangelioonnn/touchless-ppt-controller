"""Validated, versioned settings, with atomic writes and corruption recovery."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
import tempfile
import time

from app_paths import user_data_dir


@dataclass
class Settings:
    schema_version: int = 1
    camera_index: int = 0
    swap_hands: bool = True
    glow: bool = True
    preview_mode: str = 'normal'
    device: str = 'auto'
    backend: str = 'torch'  # ONNX must pass the documented promotion gate first.
    ppt_backend: str = 'com'  # Office 16: real multi-deck, forward/back and animation checks passed.

    @classmethod
    def from_dict(cls, values: dict) -> 'Settings':
        if not isinstance(values, dict):
            raise ValueError('Settings must be a JSON object.')
        allowed = {f.name for f in fields(cls)}
        result = cls(**{key: value for key, value in values.items() if key in allowed})
        if type(result.schema_version) is not int or result.schema_version != 1:
            raise ValueError('Unsupported settings version.')
        if type(result.camera_index) is not int or not 0 <= result.camera_index <= 15:
            raise ValueError('Camera number must be between 0 and 15.')
        if any(type(getattr(result, key)) is not bool for key in ('swap_hands', 'glow')):
            raise ValueError('Invalid boolean setting.')
        for key, choices in {'preview_mode': ('normal', 'overlay', 'fullscreen'),
                             'device': ('auto', 'cpu', 'cuda'),
                             'backend': ('torch', 'onnx'), 'ppt_backend': ('keys', 'com')}.items():
            if getattr(result, key) not in choices:
                raise ValueError('Invalid setting: ' + key)
        return result


class SettingsStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory if directory is not None else user_data_dir()
        self.path = self.directory / 'settings.json'
        self.warnings: list[str] = []

    def load(self) -> Settings:
        try:
            return Settings.from_dict(json.loads(self.path.read_text(encoding='utf-8')))
        except FileNotFoundError:
            return Settings()
        except (OSError, ValueError, TypeError) as error:
            self.warnings.append('Settings could not be loaded; using defaults: ' + str(error))
            try:
                if self.path.is_file():
                    self.path.rename(self.directory / ('settings.broken-' + str(time.time_ns()) + '.json'))
            except OSError:
                pass
            return Settings()

    def save(self, settings: Settings) -> bool:
        temporary = None
        try:
            validated = Settings.from_dict(asdict(settings))
            self.directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=self.directory,
                                             prefix='settings-', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(asdict(validated), stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            return True
        except (OSError, ValueError, TypeError) as error:
            self.warnings.append('Settings could not be saved: ' + str(error))
            return False
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
