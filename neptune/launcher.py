"""Locate a native Codex CLI without depending on the desktop task's PATH."""
import os
from pathlib import Path
import shutil

from .store import StoreError


def find_codex(explicit: str | None = None) -> str:
    configured = explicit or os.environ.get('NEPTUNE_CODEX_PATH')
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise StoreError(f'Configured Codex executable does not exist: {path}')
        return str(path.resolve())

    executable = shutil.which('codex')
    if executable:
        return executable

    # The Windows desktop app installs versioned native binaries here. Prefer the
    # most recently installed binary; directory names are opaque, not versions.
    local_app_data = os.environ.get('LOCALAPPDATA')
    if local_app_data:
        base = Path(local_app_data) / 'OpenAI' / 'Codex' / 'bin'
        candidates = []
        try:
            for path in [base / 'codex.exe', *base.glob('*/codex.exe')]:
                try:
                    if path.is_file():
                        candidates.append((path.stat().st_mtime_ns, str(path)))
                except OSError:
                    continue
        except OSError:
            pass
        if candidates:
            return max(candidates)[1]

    raise StoreError('Codex CLI was not found on PATH or in the desktop installation. '
                     'Use start --codex <path-to-codex.exe> or set NEPTUNE_CODEX_PATH.')
