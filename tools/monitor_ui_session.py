"""Read explicit diagnostic UI snapshots, without camera frames or desktop capture."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=660)
    args = parser.parse_args()
    records = []
    start = time.perf_counter()
    previous = None
    while time.perf_counter() - start <= args.duration:
        try:
            snapshot = json.loads(args.report.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            time.sleep(.5)
            continue
        if snapshot.get('elapsed_s') != previous:
            records.append(snapshot)
            previous = snapshot.get('elapsed_s')
            args.output.parent.mkdir(parents=True, exist_ok=True)
            hidden = [r for r in records if not r['panel_visible'] and not r['preview_drawable']]
            report = {'scope': 'native UI/worker diagnostics; no image data; not real-gesture acceptance',
                      'samples': records, 'sample_count': len(records),
                      'both_hidden_samples': len(hidden),
                      'worker_start_count_max': max(r['worker_start_count'] for r in records),
                      'model_loads_max': max(r['model_loads'] for r in records),
                      'stopped_normally': snapshot.get('phase') == 'stopped',
                      'observation_elapsed_s': time.perf_counter() - start}
            args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
            if len(records) % 30 == 0:
                print(json.dumps({'samples': len(records), 'hidden': len(hidden), 'ready': snapshot['ready'],
                                  'worker_starts': snapshot['worker_start_count'], 'model_loads': snapshot['model_loads']}), flush=True)
            if snapshot.get('phase') == 'stopped':
                break
        time.sleep(.5)
    print('UI session observations saved to ' + str(args.output), flush=True)


if __name__ == '__main__':
    main()
