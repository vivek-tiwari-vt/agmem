"""
agmem distill - Episodic-to-semantic distillation pipeline.

Converts session logs into compact facts (memory consolidation).
"""

import argparse
from pathlib import Path

from ..commands.base import require_repo
from ..core.distiller import Distiller, DistillerConfig, DistillerResult


class DistillCommand:
    """Episodic-to-semantic distillation."""

    name = "distill"
    help = "Convert episodic logs into semantic facts (memory consolidation)"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "--source",
            "-s",
            default="episodic",
            help="Source directory (default: episodic)",
        )
        parser.add_argument(
            "--target",
            "-t",
            default="semantic/consolidated",
            help="Target directory (default: semantic/consolidated)",
        )
        parser.add_argument(
            "--model",
            "-m",
            help="LLM model for extraction (e.g., gpt-4)",
        )
        parser.add_argument(
            "--no-branch",
            action="store_true",
            help="Do not create safety branch",
        )
        parser.add_argument(
            "--private",
            action="store_true",
            help="Use differential privacy (spend epsilon from budget)",
        )
        parser.add_argument(
            "--no-compress",
            action="store_true",
            help="Disable compression pipeline preprocessing",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        use_dp = getattr(args, "private", False)
        dp_epsilon = None
        dp_delta = None
        if use_dp:
            from ..core.privacy_budget import load_budget, spend_epsilon

            spent, max_eps, delta = load_budget(repo.mem_dir)
            epsilon_cost = 0.1
            if not spend_epsilon(repo.mem_dir, epsilon_cost):
                print(f"Privacy budget exceeded (spent {spent:.2f}, max {max_eps}).")
                return 1
            if spent + epsilon_cost > max_eps * 0.8:
                print(f"Privacy budget low: {spent + epsilon_cost:.2f}/{max_eps}")
            dp_epsilon = 0.05
            dp_delta = delta

        config = DistillerConfig(
            source_dir=args.source,
            target_dir=args.target,
            create_safety_branch=not args.no_branch,
            use_compression_pipeline=not getattr(args, "no_compress", False),
            use_dp=use_dp,
            dp_epsilon=dp_epsilon,
            dp_delta=dp_delta,
        )
        distiller = Distiller(repo, config)

        result = distiller.run(
            source=args.source,
            target=args.target,
            model=args.model,
        )

        print(f"Distiller completed:")
        print(f"  Clusters processed: {result.clusters_processed}")
        print(f"  Facts extracted: {result.facts_extracted}")
        print(f"  Episodes archived: {result.episodes_archived}")
        if result.branch_created:
            print(f"  Branch created: {result.branch_created}")
        if result.commit_hash:
            print(f"  Commit: {result.commit_hash[:8]}")
        print(f"\n{result.message}")

        return 0 if result.success else 1
