"""Stage a reviewable local source tree; never create a remote repository or push."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_paths import VERSION


def main():
    output = ROOT / 'build/open-source-candidate'
    output.mkdir(parents=True, exist_ok=True)
    files = list(ROOT.glob('*.py'))
    files += [ROOT / name for name in ('.gitignore', '.gitattributes', 'README.md', 'LICENSE', 'PRIVACY.md',
        'THIRD_PARTY_NOTICES.md', 'CHANGELOG.md', 'requirements.txt', 'package.json', 'launcher.js')]
    for directory in ('requirements', 'docs', 'tests', 'installer', '.github'):
        files += [p for p in (ROOT / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [p for p in (ROOT / 'tools').glob('*.py') if p.name not in ('record_baseline.py', 'benchmark_pipeline.py', 'inspect_powerpoint_api.py', 'check_original_gesture_parity.py')]
    files += list((ROOT / 'windows_launcher').glob('*.cs'))
    files += [ROOT / 'windows_launcher/TouchlessPPTController.ico', ROOT / 'models/manifest.json',
              ROOT / 'assets/touchless-ppt-icon-c1-rounded.png']
    manifest = {}
    for source in sorted(set(files)):
        if not source.is_file():
            raise RuntimeError('Public source file missing: ' + str(source))
        relative = source.relative_to(ROOT)
        if source.suffix in ('.py', '.md', '.cs', '.json', '.js', '.yml', '.txt'):
            text = source.read_text(encoding='utf-8')
            if re.search(r'[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_. -]+[\\/]|[A-Za-z]:[\\/]+Pycharm[\\/]+PythonProject', text, re.I):
                raise RuntimeError('Personal absolute path in public file: ' + str(relative))
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        with source.open('rb') as stream:
            manifest[relative.as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    (ROOT / 'validation/distribution').mkdir(parents=True, exist_ok=True)
    (ROOT / 'validation/distribution/public-source-manifest.json').write_text(json.dumps({
        'public_upload_approved': False, 'files': manifest}, indent=2), encoding='utf-8')
    archive = ROOT / ('dist/TouchlessPPTController-v%s-source-candidate.zip' % VERSION)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        # Use the explicit allowlist, never whatever happened to remain in the folder.
        for relative in manifest:
            bundle.write(output / relative, 'TouchlessPPTController/' + relative)
    artifacts = [ROOT / 'dist' / name for name in (
        'TouchlessPPTController-v%s-windows-x64-onnx-candidate-portable.zip' % VERSION,
        'TouchlessPPTController-v%s-windows-x64-setup.exe' % VERSION, archive.name,
        'TouchlessPPTController-v%s-models.zip' % VERSION)]
    checksums = []
    for path in artifacts:
        if path.is_file():
            with path.open('rb') as stream:
                checksums.append(hashlib.file_digest(stream, 'sha256').hexdigest() + '  ' + path.name)
    (ROOT / 'dist/SHA256SUMS.txt').write_text('\n'.join(checksums) + '\n', encoding='ascii')
    print('Local source candidate only: ' + str(archive))
    print('Files: ' + str(len(manifest)) + '; no repository created or uploaded.')


if __name__ == '__main__':
    main()
