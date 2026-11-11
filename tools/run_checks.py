"""Run regression checks and preserve machine-readable evidence locally."""
from __future__ import annotations
import io
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_paths import VERSION


def main():
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    start = time.perf_counter()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    report = {'version': VERSION, 'tests': result.testsRun, 'elapsed_s': time.perf_counter() - start,
              'passed': result.wasSuccessful(), 'failures': [(str(test), text) for test, text in result.failures],
              'errors': [(str(test), text) for test, text in result.errors],
              'skipped': [(str(test), reason) for test, reason in result.skipped],
              'scope': 'automated synthetic/fault tests, not a substitute for real gesture and Office acceptance'}
    output = ROOT / 'validation/regression'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'automated.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output / 'automated.txt').write_text(stream.getvalue(), encoding='utf-8')
    versioned = output / VERSION
    versioned.mkdir(exist_ok=True)
    (versioned / 'automated.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (versioned / 'automated.txt').write_text(stream.getvalue(), encoding='utf-8')
    print(stream.getvalue())
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
