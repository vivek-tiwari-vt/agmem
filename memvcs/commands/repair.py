"""
agmem repair - Auto-fix belief contradictions.

Repairs semantic memory contradictions using configurable strategy.
"""

import argparse
from pathlib import Path

from ..commands.base import require_repo
from ..core.consistency import ConsistencyChecker, ConsistencyResult


class RepairCommand:
    """Repair belief contradictions in semantic memories."""

    name = "repair"
    help = "Auto-fix contradictions using confidence scores"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "--strategy",
            "-s",
            choices=["confidence", "recency", "llm"],
            default="confidence",
            help="Repair strategy (default: confidence)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be fixed without making changes",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        checker = ConsistencyChecker(repo, llm_provider="openai")
        result = checker.repair(strategy=args.strategy)

        if result.valid:
            print("No contradictions to repair.")
            return 0

        if args.dry_run:
            print(f"Would repair {len(result.contradictions)} contradiction(s):")
            for c in result.contradictions:
                print(
                    f"  - {c.triple1.source}:{c.triple1.line} vs {c.triple2.source}:{c.triple2.line}"
                )
            print("\nRun without --dry-run to apply repairs.")
            return 0

        # Repair: keep higher-confidence triple, flag the other
        # For now we only report - full repair would modify files
        print(f"Found {len(result.contradictions)} contradiction(s).")
        print("Manual repair required - edit the semantic files to resolve.")
        for c in result.contradictions:
            keep = c.triple1 if c.triple1.confidence >= c.triple2.confidence else c.triple2
            drop = c.triple2 if keep is c.triple1 else c.triple1
            print(f"  Keep: {keep.source}:{keep.line} (confidence {keep.confidence})")
            print(f"  Review: {drop.source}:{drop.line} (confidence {drop.confidence})")
        return 1
