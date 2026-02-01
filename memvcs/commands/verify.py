"""
agmem verify - Belief consistency checker.

Scans semantic memories for logical contradictions.
"""

import argparse
from pathlib import Path

from ..commands.base import require_repo
from ..core.consistency import ConsistencyChecker, ConsistencyResult


class VerifyCommand:
    """Verify belief consistency of semantic memories."""

    name = "verify"
    help = "Scan semantic memories for logical contradictions"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "--consistency",
            "-c",
            action="store_true",
            default=True,
            help="Check for contradictions (default)",
        )
        parser.add_argument(
            "--llm",
            action="store_true",
            help="Use LLM for triple extraction (requires OpenAI)",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        checker = ConsistencyChecker(repo, llm_provider="openai" if args.llm else None)
        result = checker.check(use_llm=args.llm)

        print(f"Checked {result.files_checked} semantic file(s)")
        if result.valid:
            print("No contradictions found.")
            return 0

        print(f"\nFound {len(result.contradictions)} contradiction(s):")
        for i, c in enumerate(result.contradictions, 1):
            print(f"\n[{i}] {c.reason}")
            print(
                f"    {c.triple1.source}:{c.triple1.line}: {c.triple1.subject} {c.triple1.predicate} {c.triple1.obj}"
            )
            print(
                f"    {c.triple2.source}:{c.triple2.line}: {c.triple2.subject} {c.triple2.predicate} {c.triple2.obj}"
            )
        print("\nUse 'agmem repair --strategy confidence' to attempt auto-fix.")
        return 1
