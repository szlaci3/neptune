"""Run INSIDE the intended Codex sandbox. Never write to the Cole corpus."""
import json
import os
from pathlib import Path
import tempfile

root = Path(__file__).resolve().parents[1]
checks = {}
for label, path in {'cole': root / 'knowledge/cole-medin-knowledge-base/index.md',
                    'code': root / 'neptune/store.py'}.items():
    # Opening without truncation/writing checks access without changing source bytes.
    try:
        fd = os.open(path, os.O_WRONLY)
    except PermissionError:
        checks[label + '_write_denied'] = True
    else:
        os.close(fd)
        checks[label + '_write_denied'] = False
for label, directory in {'laci': root / 'knowledge/laci-knowledge-base', 'generated': root / 'generated'}.items():
    try:
        fd, name = tempfile.mkstemp(prefix='boundary-', dir=directory)
        os.close(fd)
        Path(name).unlink()
        checks[label + '_writable'] = True
    except PermissionError:
        checks[label + '_writable'] = False
checks['cole_readable'] = (root / 'knowledge/cole-medin-knowledge-base/index.md').read_text(encoding='utf-8').startswith('---')
print(json.dumps(checks, indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
