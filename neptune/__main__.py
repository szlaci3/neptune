"""JSON tool surface for Codex and a constrained native-runtime launcher."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys

from .store import ROOT, Store, StoreError
from tiger.core import TigerError, build_index, retrieve_packet


def route(question: str, selected: str | None = None) -> dict:
    match = re.match(r'^\s*Ask (Cole|Laci)\b\s*[:,-]?\s*', question, re.IGNORECASE)
    if match:
        kb = match[1].lower()
        if selected and selected != kb:
            raise StoreError('Explicit Ask override conflicts with selected KB')
        question = question[match.end():]
    else:
        kb = selected
    if not question.strip():
        raise StoreError('A question is required')
    return {'status': 'selected' if kb else 'needs_routing', 'kb': kb, 'question': question.strip()}


def query(question: str, selected: str | None = None, store: Store | None = None) -> dict:
    decision = route(question, selected)
    if decision['status'] != 'selected':
        return decision
    if decision['kb'] == 'cole':
        return {**retrieve_packet(decision['question']), 'kb': 'cole'}
    return (store or Store()).search(decision['question'])


def runtime_config_args() -> list[str]:
    writes = [ROOT / 'runtime', ROOT / 'knowledge' / 'laci-knowledge-base', ROOT / 'generated']
    filesystem = ','.join(json.dumps(p.as_posix()) + '="write"' for p in writes)
    # Preserve Git metadata as read-only under the writable Laci submodule.
    filesystem += ',' + json.dumps((writes[1] / '.git').as_posix()) + '="read"'
    profile = 'permissions.neptune-runtime={extends=":read-only",filesystem={' + filesystem + '},network={enabled=false}}'
    return ['-c', profile, '-c', 'default_permissions="neptune-runtime"', '-c', 'web_search="disabled"']


def runtime_command(executable: str) -> list[str]:
    # The working root is deliberately smaller than the code/corpus project.
    # No broad Neptune writable root, inherited --add-dir, or approval escalation.
    return [executable, '--cd', str(ROOT / 'runtime'), '--ask-for-approval', 'never',
            *runtime_config_args(),
            'Operate as Neptune using the neptune-assistant skill. The user will provide requests.']


def main() -> int:
    parser = argparse.ArgumentParser(prog='python -m neptune')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('setup', help='Build both disposable indexes; no model calls')
    commands.add_parser('reindex', help='Rebuild Laci discovery after fixing an indexing error')
    q = commands.add_parser('query', help='Retrieve one selected KB; Codex makes automatic routing decisions')
    q.add_argument('question')
    q.add_argument('--kb', choices=['cole', 'laci'])
    s = commands.add_parser('search', help='Find exact Laci identities')
    s.add_argument('question', nargs='?', default='')
    s.add_argument('--kind', choices=['knowledge', 'note', 'flashcard'])
    s.add_argument('--archived', action='store_true')
    s.add_argument('--limit', type=int, default=8)
    r = commands.add_parser('read')
    r.add_argument('path')
    commands.add_parser('mutate', help='Read a mutation JSON object from stdin')
    d = commands.add_parser('due')
    d.add_argument('--deck')
    launch = commands.add_parser('start', help='Start interactive Codex with restricted write roots')
    launch.add_argument('--show-command', action='store_true')
    args = parser.parse_args()
    store = Store()
    try:
        if args.command == 'setup':
            result = {'cole': build_index()}
            with store.locked():
                result['laci'] = store.reindex()
        elif args.command == 'reindex':
            with store.locked():
                result = store.reindex()
        elif args.command == 'query':
            result = query(args.question, args.kb, store)
        elif args.command == 'search':
            result = store.search(args.question, kind=args.kind, archived=args.archived, limit=args.limit)
        elif args.command == 'read':
            result = store.read(args.path)
        elif args.command == 'mutate':
            request = json.load(sys.stdin)
            if not isinstance(request, dict):
                raise StoreError('Mutation must be a JSON object')
            result = store.mutate(request)
        elif args.command == 'due':
            result = store.due(args.deck)
        elif args.command == 'start':
            executable = shutil.which('codex')
            if not executable:
                raise StoreError('Codex CLI is not installed or not on PATH')
            command = runtime_command(executable)
            if args.show_command:
                result = {'argv': command}
            else:
                (ROOT / 'generated').mkdir(exist_ok=True)
                env = {**os.environ, 'PYTHONPATH': str(ROOT), 'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
                return subprocess.call(command, env=env)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (StoreError, TigerError, OSError, sqlite3.Error, ValueError, TypeError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
