"""Validate relocated packaged inference and an optional disposable installer run.

This does not claim a clean Windows VM: installed OS components remain available.
It never opens a camera or alters an existing registered installation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_paths import VERSION


def check_worker(folder: Path, output: Path):
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(('PYTHON', 'CONDA')) and key != 'TOUCHLESS_PPT_EXTRA_SITE'}
    env['PATH'] = str(Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32')
    env['TOUCHLESS_PPT_DATA_DIR'] = str(output / 'app-data')
    env['PYTHONIOENCODING'] = 'utf-8'
    executable = folder / 'runtime/ControllerWorker.exe'
    process = subprocess.run([str(executable), '--self-check', '--backend', 'onnx', '--device', 'cpu'],
                             cwd=os.environ.get('WINDIR', r'C:\Windows'), env=env, capture_output=True,
                             text=True, encoding='utf-8', errors='replace', timeout=30,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    result = json.loads(process.stdout.strip().splitlines()[-1]) if process.stdout.strip() else {}
    inside = all(str(Path(result.get(key, '')).resolve()).startswith(str(folder.resolve()))
                 for key in ('numpy_location', 'cv2_location'))
    return {'exit_code': process.returncode, 'result': result,
            'passed': process.returncode == 0 and result.get('inference_ok') is True
                      and result.get('version') == VERSION
                      and result.get('frozen') is True and result.get('torch_imported') is False and inside,
            'stderr': process.stderr[-2000:]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cross-drive-root', type=Path)
    parser.add_argument('--installer', type=Path)
    args = parser.parse_args()
    source = ROOT / ('dist/TouchlessPPTController-v%s-onnx-candidate' % VERSION)
    output = ROOT / 'validation/distribution' / VERSION
    output.mkdir(parents=True, exist_ok=True)
    with (source / 'build-report.json').open('rb') as stream:
        build_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
    report = {'version': VERSION, 'build_report_sha256': build_sha256,
              'clean_windows_vm_verified': False, 'network_disconnected_test': False, 'paths': []}
    destinations = [output / '中文 空格目录/App']
    if args.cross_drive_root:
        destinations.append(args.cross_drive_root.resolve() / 'Touchless 路径测试/App')
    for destination in destinations:
        shutil.copytree(source, destination, dirs_exist_ok=True)
        result = check_worker(destination, output)
        report['paths'].append({'directory': str(destination), **result})
        print(json.dumps({'directory': str(destination), 'passed': result['passed']}, ensure_ascii=True), flush=True)
    if args.installer:
        import winreg
        with args.installer.open('rb') as stream:
            report['installer_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
        target = output / '安装目录 with spaces'
        key = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{9F6266D1-8C74-4D65-9F87-BF470B3E2647}_is1'
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as handle:
                installed = Path(winreg.QueryValueEx(handle, 'InstallLocation')[0]).resolve()
                if installed != target.resolve():
                    raise RuntimeError('An existing user installation is registered; refusing to alter it.')
        except FileNotFoundError:
            pass
        process = subprocess.run([str(args.installer.resolve()), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                                  '/NOICONS', '/TASKS=', '/DIR=' + str(target), '/LOG=' + str(output / 'install.log')],
                                 timeout=180)
        install = {'exit_code': process.returncode}
        if process.returncode == 0:
            install['inference'] = check_worker(target, output)
            sentinel = target / 'unowned-user-file.txt'
            sentinel.write_text('Test fixture: the uninstaller must preserve unowned files.', encoding='utf-8')
            uninstaller = target / 'unins000.exe'
            removal = subprocess.run([str(uninstaller), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                                      '/LOG=' + str(output / 'uninstall.log')], timeout=120)
            install['uninstall_exit_code'] = removal.returncode
            install['installed_exe_removed'] = not (target / 'TouchlessPPTController.exe').exists()
            install['unowned_file_preserved'] = sentinel.is_file()
            install['user_data_preserved'] = (output / 'app-data').is_dir()
        report['installer'] = install
    (output / 'distribution-checks.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if not all(item['passed'] for item in report['paths']):
        raise SystemExit(1)
    if args.installer:
        install = report['installer']
        if not (install['exit_code'] == 0 and install.get('inference', {}).get('passed')
                and install.get('uninstall_exit_code') == 0
                and all(install.get(key) for key in ('installed_exe_removed', 'unowned_file_preserved', 'user_data_preserved'))):
            raise SystemExit('Installer/uninstaller checks failed; see the report.')
    print('Relocation checks saved; clean-machine and true-offline checks remain pending.')


if __name__ == '__main__':
    main()
