"""
agmem decay - Memory decay and forgetting.

Archives low-importance, rarely-accessed memories.
"""

import argparse
from pathlib import Path

from ..commands.base import require_repo
from ..core.decay import DecayEngine, DecayConfig


class DecayCommand:
    """Memory decay - archive low-importance memories."""

    name = "decay"
    help = "Archive low-importance, old episodic memories (decay/forgetting)"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be archived without making changes",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually archive the memories",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        config = DecayConfig()
        repo_config = repo.get_config()
        decay_cfg = repo_config.get("decay", {})
        if decay_cfg:
            config.episodic_half_life_days = decay_cfg.get(
                "episodic_half_life_days", config.episodic_half_life_days
            )
            config.semantic_min_importance = decay_cfg.get(
                "semantic_min_importance", config.semantic_min_importance
            )
            config.access_count_threshold = decay_cfg.get(
                "access_count_threshold", config.access_count_threshold
            )

        engine = DecayEngine(repo, config)
        candidates = engine.get_decay_candidates()

        if not candidates:
            print("No memories eligible for decay.")
            return 0

        print(f"Found {len(candidates)} memory(ies) eligible for decay:")
        for c in candidates[:20]:
            print(f"  - {c.path} (score: {c.decay_score:.2f}) - {c.reason}")
        if len(candidates) > 20:
            print(f"  ... and {len(candidates) - 20} more")

        if args.dry_run:
            print("\nDry run - no changes made. Use --apply to archive.")
            return 0

        if not args.apply:
            print("\nUse --apply to archive these memories.")
            return 0

        count = engine.apply_decay(candidates)
        print(f"\nArchived {count} memory(ies) to .mem/forgetting/")
        print("Use 'agmem resurrect <path>' to restore.")
        return 0
