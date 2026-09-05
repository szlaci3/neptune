"""Host-side boundary check using the exact launcher's permission profile."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from neptune.__main__ import runtime_config_args

command = [shutil.which('codex') or 'codex', 'sandbox', '-P', 'neptune-runtime',
           '-C', str(root / 'runtime'), *runtime_config_args(), sys.executable, '-X', 'utf8',
           str(root / 'scripts/check_runtime_boundary.py')]
result = subprocess.run(command, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, timeout=60)
raise SystemExit(result.returncode)
