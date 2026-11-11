"""Build the native control panel; local interpreter configuration stays untracked."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def build(output: Path, python: str | None = None, backend: str = 'torch', portable=False):
    compiler = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.is_file():
        raise RuntimeError('The Windows .NET Framework C# compiler was not found.')
    output.mkdir(parents=True, exist_ok=True)
    destination = output / 'TouchlessPPTController.exe'
    subprocess.run([str(compiler), '/nologo', '/target:winexe', '/platform:x64', '/optimize+', '/codepage:65001',
                    '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll', '/reference:System.Web.Extensions.dll', '/reference:System.Core.dll',
                    '/win32icon:' + str(ROOT / 'windows_launcher/TouchlessPPTController.ico'),
                    '/out:' + str(destination),
                    *[str(path) for path in sorted((ROOT / 'windows_launcher').glob('*.cs')) if path.name != 'NativeUiTests.cs']], check=True)
    if portable:
        config = {'worker': 'runtime/ControllerWorker.exe', 'backend': backend, 'candidate': backend == 'onnx'}
    else:
        config = {'python': python or sys.executable, 'script': os.path.relpath(ROOT / 'ppt_controller.py', output),
                  'backend': backend, 'extra_site': os.path.relpath(ROOT / '.venv-release/Lib/site-packages', output)}
    (output / 'launcher.runtime.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    import shutil
    (output / 'windows_launcher').mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'windows_launcher/TouchlessPPTController.ico', output / 'windows_launcher/TouchlessPPTController.ico')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=ROOT / 'build/development')
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--backend', choices=('torch', 'onnx'), default='torch')
    parser.add_argument('--portable', action='store_true')
    args = parser.parse_args()
    print(build(args.out.resolve(), args.python, args.backend, args.portable))
