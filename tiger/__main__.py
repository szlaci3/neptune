"""Command interface for tiger discovery, evidence packets, and one-response prompts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import DEFAULT_RETRIEVED_CHUNKS, DEFAULT_CORPUS, DEFAULT_INDEX, TigerError, build_index, packet_prompt, retrieve_packet


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tiger", description="Neptune bounded Cole OKF retrieval")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build", help="rebuild disposable FTS discovery data")
    retrieve = commands.add_parser("retrieve", help="write a bounded evidence packet as JSON")
    retrieve.add_argument("question")
    retrieve.add_argument("--limit", type=int, default=DEFAULT_RETRIEVED_CHUNKS)
    prompt = commands.add_parser("prompt", help="write the fixed context for one Codex response")
    prompt.add_argument("question")
    prompt.add_argument("--limit", type=int, default=DEFAULT_RETRIEVED_CHUNKS)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "build":
            print(json.dumps(build_index(args.corpus, args.index), sort_keys=True))
            return 0
        packet = retrieve_packet(args.question, args.corpus, args.index, limit=args.limit)
        print(packet_prompt(packet) if args.command == "prompt" else json.dumps(packet, ensure_ascii=False, indent=2))
        return 0
    except TigerError as exc:
        print(f"tiger: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
