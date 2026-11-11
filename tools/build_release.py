"""Build a self-contained ONNX candidate without inheriting the Conda environment."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_paths import VERSION
from tools.build_launcher import build as build_launcher


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def collect_licenses(output):
    components = {}
    for name in ('numpy', 'opencv-python', 'onnxruntime', 'pywin32', 'flatbuffers', 'protobuf', 'packaging', 'psutil', 'pyinstaller'):
        distribution = metadata.distribution(name)
        components[name] = distribution.version
        for item in distribution.files or []:
            if any(word in Path(str(item)).name.lower() for word in ('license', 'copying', 'notice')):
                source = Path(distribution.locate_file(item)).resolve()
                if not source.is_file():
                    continue
                parts = [part for part in Path(str(item)).parts if part not in ('.', '..', '/', '\\')]
                destination = output / 'third_party_licenses' / name / Path(*parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
    base = Path(sys.base_prefix)
    for source in (base / 'LICENSE.txt', base / 'LICENSE', base / 'Lib/LICENSE.txt'):
        if source.is_file():
            destination = output / 'third_party_licenses/Python'
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination / source.name)
    return components


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--iscc', type=Path)
    parser.add_argument('--reuse-worker', action='store_true', help='Only reuse a worker built from the identical sources')
    args = parser.parse_args()
    model = ROOT / 'models/yolo26s-pose.onnx'
    if not model.is_file():
        raise SystemExit('Export the pinned ONNX model before building.')
    manifest = json.loads((ROOT / 'models/manifest.json').read_text(encoding='utf-8'))
    if digest(model) != manifest['onnx_sha256']:
        raise SystemExit('ONNX hash mismatch; refusing to package a different model.')
    build_dir = ROOT / 'build'
    worker_dir = build_dir / 'pyinstaller-dist/ControllerWorker'
    sources = {str(p.relative_to(ROOT)): digest(p) for p in ROOT.glob('*.py')}
    source_record = build_dir / 'worker-source-hashes.json'
    if args.reuse_worker:
        if not source_record.is_file() or json.loads(source_record.read_text(encoding='utf-8')) != sources:
            raise SystemExit('Source changed since worker build; omit --reuse-worker.')
    else:
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--console',
            '--name', 'ControllerWorker', '--distpath', str(build_dir / 'pyinstaller-dist'),
            '--workpath', str(build_dir / 'pyinstaller-work'), '--specpath', str(build_dir / 'spec'),
            '--icon', str(ROOT / 'windows_launcher/TouchlessPPTController.ico'),
            '--exclude-module', 'torch', '--exclude-module', 'torchvision', '--exclude-module', 'ultralytics',
            '--exclude-module', 'onnx', '--exclude-module', 'onnxscript', '--exclude-module', 'onnxslim',
            '--exclude-module', 'PIL',
            '--hidden-import', 'win32com.client', '--hidden-import', 'pythoncom', '--hidden-import', 'pywintypes',
            '--add-data', str(model) + ';models',
            '--add-data', str(ROOT / 'models/manifest.json') + ';models',
            '--add-data', str(ROOT / 'windows_launcher/TouchlessPPTController.ico') + ';windows_launcher',
            str(ROOT / 'ppt_controller.py')], cwd=ROOT, check=True)
        source_record.write_text(json.dumps(sources, indent=2), encoding='utf-8')
    if not (worker_dir / 'ControllerWorker.exe').is_file():
        raise SystemExit('Worker build missing.')
    destination = ROOT / 'dist' / ('TouchlessPPTController-v%s-onnx-candidate' % VERSION)
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(worker_dir, destination / 'runtime', dirs_exist_ok=True)
    build_launcher(destination, backend='onnx', portable=True)
    for name in ('LICENSE', 'README.md', 'PRIVACY.md', 'THIRD_PARTY_NOTICES.md', 'CHANGELOG.md'):
        shutil.copy2(ROOT / name, destination / name)
    (destination / 'docs').mkdir(exist_ok=True)
    shutil.copytree(ROOT / 'docs', destination / 'docs', dirs_exist_ok=True)
    components = collect_licenses(destination)
    ppt_evidence = ROOT / 'validation/powerpoint/integration.json'
    ppt = json.loads(ppt_evidence.read_text(encoding='utf-8')) if ppt_evidence.is_file() else {}
    required_ppt = ('forward_20', 'back_20', 'other_document_untouched', 'com_next_preserves_animation_step',
                    'com_previous_preserves_animation_step', 'closed_target_no_reassignment')
    com_verified = all(ppt.get('tests', {}).get(name) is True for name in required_ppt)
    pending = ['real gestures and event replay', 'clean Windows install', 'OS cold-start']
    if not com_verified:
        pending.append('PowerPoint animations and multi-document control')
    report = {'version': VERSION, 'candidate': True, 'default_backend': 'onnx', 'default_ppt_backend': 'com',
              'presenter_policy': 'single-presenter-auto-resume', 'absence_auto_lock': False,
              'native_preview': True, 'tray_background': True, 'ui_preferences_schema': 1,
              'torch_included': False, 'components': components, 'model': manifest, 'worker_source_sha256': sources,
              'public_release_approved': False,
              'reference_ppt_verified': com_verified, 'reference_office_version': ppt.get('office_version'),
              'keys_windowed_verified': ppt.get('tests', {}).get('targeted_key_reaches_slideshow'),
              'pending': pending,
              'files': {str(p.relative_to(destination)).replace('\\', '/'): {'size': p.stat().st_size, 'sha256': digest(p)}
                        for p in sorted(destination.rglob('*')) if p.is_file() and p.name != 'build-report.json'}}
    (destination / 'build-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    archive = ROOT / 'dist' / ('TouchlessPPTController-v%s-windows-x64-onnx-candidate-portable.zip' % VERSION)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(destination.rglob('*')):
            if path.is_file():
                bundle.write(path, str(Path(destination.name) / path.relative_to(destination)))
    artifacts = [archive]
    if args.iscc:
        subprocess.run([str(args.iscc), '/DSourceDir=' + str(destination), '/DOutputDir=' + str(ROOT / 'dist'),
                        str(ROOT / 'installer/TouchlessPPTController.iss')], cwd=ROOT, check=True)
        artifacts.append(ROOT / 'dist' / ('TouchlessPPTController-v%s-windows-x64-setup.exe' % VERSION))
    source_archive = ROOT / 'dist' / ('TouchlessPPTController-v%s-source-candidate.zip' % VERSION)
    if source_archive.is_file():
        artifacts.append(source_archive)
    sums = '\n'.join(digest(path) + '  ' + path.name for path in artifacts) + '\n'
    (ROOT / 'dist/SHA256SUMS.txt').write_text(sums, encoding='ascii')
    print('Candidate only; do not publish before acceptance.')
    print(destination)
    print(sums)


if __name__ == '__main__':
    main()
