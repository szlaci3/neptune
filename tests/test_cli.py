"""Exercise the public stdin/stdout interface against an isolated installed copy."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class CLITests(unittest.TestCase):
    def test_note_to_knowledge_and_flashcard_through_real_commands(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for package in ('neptune', 'tiger'):
                shutil.copytree(source / package, root / package, ignore=shutil.ignore_patterns('__pycache__'))

            def call(*args, data=None, code=0):
                result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'neptune', *args],
                                        cwd=root, input=json.dumps(data) if data is not None else None,
                                        capture_output=True, text=True, encoding='utf-8',
                                        env={**os.environ, 'PYTHONPATH': str(root)}, timeout=20)
                self.assertEqual(result.returncode, code, result.stderr)
                return json.loads(result.stdout if code == 0 else result.stderr)

            self.assertEqual(call('query', 'Ask Laci: JavaScript')['status'], 'insufficient_coverage')
            note = call('mutate', data={'action': 'create', 'authorized': True, 'metadata': {
                'type': 'note', 'title': 'Numeric separators'}, 'body': 'JavaScript accepts 4_000 as 4000.'})['record']
            self.assertEqual(call('search', 'separators', '--kind', 'note')['records'][0]['path'], note['path'])
            promoted = call('mutate', data={'action': 'promote', 'authorized': True, 'path': note['path'],
                                           'expected_revision': note['revision']})['record']
            self.assertEqual(promoted['metadata']['type'], 'knowledge')
            card = call('mutate', data={'action': 'create', 'authorized': True, 'metadata': {
                'type': 'flashcard', 'title': 'Numeric separators', 'front': 'What is 4_000?', 'back': '4000'}})['record']
            self.assertEqual(call('due')['cards'][0]['path'], card['path'])
            call('mutate', data={'action': 'review', 'authorized': True, 'path': card['path'],
                                 'expected_revision': card['revision'], 'rating': 'good'})
            self.assertEqual(call('due')['cards'], [])
            call('mutate', data={'action': 'delete', 'authorized': True, 'path': promoted['path'],
                                 'expected_revision': promoted['revision']})
            self.assertEqual(call('search', '--kind', 'knowledge')['records'], [])
            error = call('mutate', data={'action': 'create', 'authorized': True, 'kb': 'cole'}, code=2)
            self.assertIn('read-only', error['error'])


if __name__ == '__main__':
    unittest.main()
