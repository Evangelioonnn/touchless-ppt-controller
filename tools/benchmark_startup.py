"""Repeated camera readiness trials. New processes are never labelled OS cold starts."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import queue
import statistics
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_paths import VERSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--backend', choices=('torch', 'onnx'), default='onnx')
    parser.add_argument('--runs', type=int, default=10)
    args = parser.parse_args()
    output = ROOT / 'validation/startup' / VERSION / (args.backend + ('-packaged' if args.worker else '-source'))
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for number in range(args.runs):
        data_dir = output / ('trial-%02d' % (number + 1))
        env = {**os.environ, 'TOUCHLESS_PPT_DATA_DIR': str(data_dir), 'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1'}
        command = [str(args.worker)] if args.worker else [args.python, '-B', '-u', str(ROOT / 'ppt_controller.py')]
        command += ['--protocol', '--headless', '--observe-only', '--backend', args.backend, '--duration', '55']
        before = time.perf_counter()
        lines: queue.Queue = queue.Queue()
        with (output / ('stderr-%02d.txt' % number)).open('w', encoding='utf-8') as errors:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=errors, text=True, encoding='utf-8', bufsize=1,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            def reader():
                for line in process.stdout:
                    try:
                        lines.put(json.loads(line))
                    except ValueError:
                        pass
            thread = threading.Thread(target=reader, daemon=True); thread.start()
            record = {'trial': number + 1, 'stages': {}}
            deadline = time.perf_counter() + 60
            while time.perf_counter() < deadline and process.poll() is None:
                try:
                    message = lines.get(timeout=.2)
                except queue.Empty:
                    continue
                if message.get('type') == 'stage':
                    record['stages'][message['stage']] = message['elapsed_s']
                    if message['stage'] == 'ready':
                        record['ready_wall_s'] = time.perf_counter() - before
                        break
                if message.get('type') == 'error':
                    record['error'] = message.get('message')
                    break
            try:
                process.stdin.write('{"action":"quit"}\n'); process.stdin.flush()
            except (OSError, ValueError):
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(); record['forced_exit'] = True
            record['exit_code'] = process.returncode
            thread.join(1)
        records.append(record)
        report = {'version': VERSION, 'measurement': 'repeated new-process CAMERA readiness, NOT OS cold-start trials',
                  'backend': args.backend, 'records': records,
                  'ready_median_s': statistics.median([r['ready_wall_s'] for r in records if 'ready_wall_s' in r]) if any('ready_wall_s' in r for r in records) else None,
                  'os_cold_start_verified': False}
        (output / 'trials.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(record), flush=True)
    print(json.dumps({key: value for key, value in report.items() if key != 'records'}, indent=2))


if __name__ == '__main__':
    main()
