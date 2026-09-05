import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from neptune.launcher import find_codex
from neptune.store import StoreError


class LauncherTests(unittest.TestCase):
    def test_desktop_discovery_without_path_prefers_newest_binary(self):
        with tempfile.TemporaryDirectory() as name:
            base = Path(name) / 'OpenAI/Codex/bin'
            older = base / 'zzz-opaque-id/codex.exe'
            newer = base / 'aaa-opaque-id/codex.exe'
            for path in (older, newer):
                path.parent.mkdir(parents=True)
                path.write_bytes(b'test fixture; never executed')
            os.utime(older, (100, 100))
            os.utime(newer, (200, 200))
            with patch.dict(os.environ, {'LOCALAPPDATA': name}, clear=True), patch('neptune.launcher.shutil.which', return_value=None):
                self.assertEqual(find_codex(), str(newer))

    def test_explicit_and_environment_paths_override_path(self):
        with tempfile.TemporaryDirectory() as name:
            executable = Path(name) / 'codex.exe'
            executable.touch()
            with patch.dict(os.environ, {'NEPTUNE_CODEX_PATH': str(executable)}, clear=True), patch('neptune.launcher.shutil.which', return_value='path-codex'):
                self.assertEqual(find_codex(), str(executable.resolve()))
                with self.assertRaisesRegex(StoreError, 'Configured Codex'):
                    find_codex(str(executable.parent / 'missing.exe'))

    def test_path_is_preferred_and_missing_installation_has_actionable_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch('neptune.launcher.shutil.which', return_value='path-codex'):
                self.assertEqual(find_codex(), 'path-codex')
            with patch('neptune.launcher.shutil.which', return_value=None):
                with self.assertRaisesRegex(StoreError, 'start --codex'):
                    find_codex()
