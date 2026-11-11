"""Compile native component tests; render only synthetic/offscreen UI, no camera."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    compiler = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    output = ROOT / 'validation/ui-tray/native'
    output.mkdir(parents=True, exist_ok=True)
    executable = output / 'NativeUiTests.exe'
    subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64', '/codepage:65001',
        '/main:TouchlessPPTControllerLauncher.NativeUiTests', '/out:' + str(executable),
        '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll', '/reference:System.Web.Extensions.dll', '/reference:System.Core.dll',
        *[str(p) for p in sorted((ROOT / 'windows_launcher').glob('*.cs'))]], check=True)
    subprocess.run([str(executable), str(output)], cwd=ROOT, check=True, timeout=120)


if __name__ == '__main__':
    main()
