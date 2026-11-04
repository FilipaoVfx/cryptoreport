"""Run repository-supported suites without invoking collection or paid analysis."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ('analysis', ['-m', 'unittest', 'discover', '-s', 'tests', '-t', '.']),
    ('transcripts', ['-m', 'unittest', 'discover', '-s', 'tests', '-t', '.']),
    ('bridge', ['-m', 'unittest', 'discover', '-s', 'tests', '-t', '.']),
    ('social', ['-m', 'unittest', 'discover', '-s', 'tests']),
    ('panel', ['-B', '-m', 'unittest', 'discover', '-s', 'tests']),
]
env = {**os.environ, 'CRA_ALLOW_API_ANALYSIS': 'false'}
failed = False
for service, args in CASES:
    print(f'\n=== {service} ===', flush=True)
    case_env = {**env, 'PYTHONPATH': str(ROOT / 'services/analysis') + os.pathsep + str(ROOT / 'services/transcripts')}
    code = subprocess.run([sys.executable, *args], cwd=ROOT / 'services' / service, env=case_env, timeout=180).returncode
    failed |= code != 0
print('\n=== mobile data and runtime ===', flush=True)
failed |= subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'prototypes/movil', '-p', 'test_*.py'], cwd=ROOT, env=env, timeout=180).returncode != 0
print('\n=== observability contracts ===', flush=True)
failed |= subprocess.run([sys.executable, 'docs/observabilidad/herramientas/validate_contracts.py'], cwd=ROOT, env=env, timeout=60).returncode != 0
failed |= subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'docs/observabilidad/herramientas/tests', '-t', 'docs/observabilidad/herramientas'], cwd=ROOT, env=env, timeout=60).returncode != 0
sys.exit(int(failed))
