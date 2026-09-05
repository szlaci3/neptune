from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sqlite3
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from neptune.__main__ import query, route, runtime_command
from neptune.store import Store, StoreError
from tiger.core import TigerError, _source_packet, _valid_video_url, timestamp_seconds


class NeptuneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.store = Store(self.base / 'laci', self.base / 'generated' / 'laci.sqlite')

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, kind='knowledge', title='Belgian cycling', body='Ride by the river.', **metadata):
        return self.store.mutate({'action': 'create', 'authorized': True,
                                 'metadata': {'type': kind, 'title': title, **metadata}, 'body': body})

    def change(self, record, action='update', **fields):
        return self.store.mutate({'action': action, 'authorized': True, 'path': record['path'],
                                 'expected_revision': record['revision'], **fields})

    def test_explicit_routing_wins_and_automatic_decision_belongs_to_codex(self):
        self.assertEqual(route('Ask Cole: What is RAG?')['kb'], 'cole')
        self.assertEqual(route('Ask Laci where do I cycle?')['kb'], 'laci')
        self.assertEqual(route('Where do I cycle?')['status'], 'needs_routing')
        self.assertEqual(route('A note says "Ask Cole"')['status'], 'needs_routing')
        with self.assertRaises(StoreError):
            route('Ask Cole: RAG', 'laci')
        with self.assertRaises(StoreError):
            route('Ask Cole')

    def test_laci_route_cannot_accidentally_retrieve_cole(self):
        with patch('neptune.__main__.retrieve_packet', side_effect=AssertionError('Cole queried')):
            packet = query('Ask Laci where do I cycle?', store=self.store)
        self.assertEqual(packet['status'], 'insufficient_coverage')
        self.assertEqual(packet['records'], [])

    def test_save_search_edit_delete_and_automatic_index(self):
        result = self.create()
        self.assertTrue(result['indexed'])
        record = result['record']
        self.assertEqual(record['metadata']['Date'], date.today().isoformat())
        search = self.store.search('cycling')
        self.assertEqual(search['discovery'], 'fts5')
        self.assertEqual(search['records'][0]['path'], record['path'])
        edited = self.change(record, body='Ride by the canal.')['record']
        self.assertEqual(edited['path'], record['path'])
        self.assertIn('canal', self.store.search('canal')['records'][0]['body'])
        self.assertNotEqual(edited['revision'], record['revision'])
        deleted = self.change(edited, 'delete')
        self.assertTrue(deleted['indexed'])
        self.assertEqual(self.store.search('canal')['records'], [])

    def test_authorization_and_cole_are_required_boundaries(self):
        for request in ({'action': 'create'}, {'action': 'create', 'authorized': 'yes'},
                        {'action': 'create', 'authorized': True, 'kb': 'cole'}):
            with self.assertRaises(StoreError):
                self.store.mutate(request)
        self.assertFalse(self.store.root.exists())

    def test_conflicting_edit_and_ambiguous_identity_do_not_overwrite(self):
        original = self.create()['record']
        self.create(title='Belgian cycling')
        self.assertEqual(self.store.search('cycling')['total'], 2)
        current = self.change(original, body='An intervening edit.')['record']
        with self.assertRaisesRegex(StoreError, 'Revision conflict'):
            self.change(original, body='Stale overwrite')
        self.assertEqual(self.store.read(original['path']), current)
        with self.assertRaises(StoreError):
            self.store.read('Belgian cycling')

    def test_path_traversal_absolute_and_symlink_escape_are_rejected(self):
        for name in ('../cole/file.md', 'records/../../file.md', 'C:/file.md', 'records/a/b.md', 'records/CON:stream.md'):
            with self.assertRaises(StoreError):
                self.store.path(name)
        self.store.root.mkdir()
        (self.store.root / 'records').mkdir()
        outside = self.base / 'outside.md'
        outside.write_text('protected', encoding='utf-8')
        try:
            (self.store.root / 'records' / 'link.md').symlink_to(outside)
        except OSError:
            return  # Windows sandbox may not grant symlink creation.
        with self.assertRaises(StoreError):
            self.store.read('records/link.md')

    def test_failed_index_preserves_saved_record_and_search(self):
        with patch.object(self.store, 'reindex', side_effect=sqlite3.OperationalError('disk full')):
            result = self.create()
        self.assertEqual(result['status'], 'saved_index_failed')
        self.assertTrue(result['saved'])
        self.assertFalse(result['indexed'])
        self.assertIn('disk full', result['error'])
        self.assertEqual(self.store.search('cycling')['records'][0]['path'], result['path'])
        with self.store.locked():
            self.store.reindex()
        self.assertEqual(self.store.search('cycling')['discovery'], 'fts5')

    def test_stale_missing_and_corrupt_indexes_fall_back_to_canonical_content(self):
        record = self.create()['record']
        # Simulate an external editor, outside the supported mutation tool.
        target = self.store.path(record['path'])
        target.write_text(target.read_text(encoding='utf-8').replace('river', 'orchard'), encoding='utf-8')
        result = self.store.search('orchard')
        self.assertEqual(result['discovery'], 'canonical')
        self.assertIn('orchard', result['records'][0]['body'])
        self.store.index.unlink()
        self.assertEqual(self.store.search('orchard')['total'], 1)
        self.store.index.write_bytes(b'not a database')
        self.assertEqual(self.store.search('orchard')['total'], 1)

    def test_notes_archive_restore_and_promote_in_place(self):
        record = self.create(kind='note')['record']
        archived = self.change(record, 'archive')['record']
        self.assertEqual(self.store.search('cycling')['total'], 0)
        self.assertEqual(self.store.search('cycling', archived=True)['total'], 1)
        restored = self.change(archived, 'restore')['record']
        promoted = self.change(restored, 'promote')['record']
        self.assertEqual(promoted['path'], record['path'])
        self.assertEqual(promoted['metadata']['type'], 'knowledge')
        self.assertEqual(self.store.search('cycling', kind='note')['total'], 0)

    def test_flashcard_creation_edit_and_user_review(self):
        card = self.create(kind='flashcard', title='Numeric separators', front='What is 4_000?', back='4000', deck='JavaScript')['record']
        self.assertEqual(self.store.due('JavaScript')['cards'][0]['path'], card['path'])
        reviewed = self.change(card, 'review', rating='easy')['record']
        self.assertEqual(reviewed['metadata']['interval'], 4)
        self.assertEqual(self.store.due()['total'], 0)
        again = self.change(reviewed, 'review', rating='again')['record']
        self.assertEqual(self.store.due()['total'], 1)
        edited = self.change(again, metadata={'back': 'The numeric value 4000.'})['record']
        self.assertIn('The numeric value 4000.', edited['body'])
        with self.assertRaises(StoreError):
            self.change(edited, 'review', rating='invented')

    def test_writer_lock_and_failed_replace_leave_previous_record(self):
        record = self.create()['record']
        with self.store.locked():
            with self.assertRaisesRegex(StoreError, 'Another write'):
                self.change(record, body='Blocked')
        with patch('neptune.store.os.replace', side_effect=OSError('injected write failure')):
            with self.assertRaises(OSError):
                self.change(record, body='Must not replace')
        self.assertEqual(self.store.read(record['path']), record)
        self.assertFalse((self.store.root / '.neptune-write.lock').exists())

    def test_unicode_metadata_and_literal_shell_content_round_trip(self):
        text = "Magyar: őrült; 日本語. $(Get-Secret) `echo` \n---\nQuoted 'text'."
        record = self.create(title='日本語', body=text, Author='László', Context='A: B')['record']
        self.assertEqual(record['body'], text)
        self.assertEqual(record['metadata']['Author'], 'László')
        self.assertEqual(self.store.search('日本語')['total'], 1)

    def test_invalid_metadata_is_not_saved(self):
        for metadata in ({'Date': '2026-02-30'}, {'Author': ['bad']}, {'type': 'unknown'}):
            with self.assertRaises(StoreError):
                self.store.mutate({'action': 'create', 'authorized': True,
                                   'metadata': {'title': 'test', **metadata}, 'body': 'text'})
        self.assertEqual(list(self.store.records()), [])

    def test_launcher_uses_small_write_roots_and_no_approval_escalation(self):
        args = runtime_command('codex')
        self.assertEqual(args[args.index('--ask-for-approval') + 1], 'never')
        profile_arg = next(arg for arg in args if arg.startswith('permissions.neptune-runtime='))
        profile = tomllib.loads(profile_arg)['permissions']['neptune-runtime']
        roots = [Path(p) for p, access in profile['filesystem'].items() if access == 'write']
        self.assertEqual({p.name for p in roots}, {'runtime', 'laci-knowledge-base', 'generated'})
        self.assertEqual(profile['extends'], ':read-only')
        self.assertFalse(profile['network']['enabled'])
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', args)


class ProvenanceTests(unittest.TestCase):
    def test_timestamp_range_and_video_scheme_validation(self):
        self.assertEqual(timestamp_seconds('01:23:45'), 5025)
        for value in ('01:60:00', '00:00:60', 'no timestamp'):
            with self.assertRaises(TigerError):
                timestamp_seconds(value)
        self.assertFalse(_valid_video_url('http://youtu.be/13HP_bSeNjU', '13HP_bSeNjU'))
        self.assertFalse(_valid_video_url('https://youtube.com.evil/watch?v=13HP_bSeNjU', '13HP_bSeNjU'))

    def test_malformed_source_is_rejected_without_fabricated_video(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'sources').mkdir()
            for video_id, published in [('invalid', '2026-01-01'), ('13HP_bSeNjU', '2026-02-30')]:
                (root / 'sources' / 'bad.md').write_text(
                    f'---\ntype: source\ntitle: Bad\nyoutube_id: {video_id}\nurl: https://youtu.be/{video_id}\npublished: {published}\n---\n# Bad\n', encoding='utf-8')
                with self.assertRaises(TigerError):
                    _source_packet(root, 'sources/bad.md', [])


if __name__ == '__main__':
    unittest.main()
