"""
agmem garden - Run the Gardener to synthesize episodic memories into insights.
"""

import argparse

from ..commands.base import require_repo
from ..core.gardener import Gardener, GardenerConfig


class GardenCommand:
    """Run the Gardener reflection loop."""

    name = "garden"
    help = "Synthesize episodic memories into semantic insights"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "--force", action="store_true", help="Run even if episode threshold not met"
        )
        parser.add_argument(
            "--threshold",
            type=int,
            default=50,
            help="Number of episodes before auto-triggering (default: 50)",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Show what would be done without making changes"
        )
        parser.add_argument(
            "--no-commit", action="store_true", help="Do not auto-commit generated insights"
        )
        parser.add_argument(
            "--llm",
            choices=["openai", "none"],
            default="none",
            help="LLM provider for summarization (default: none)",
        )
        parser.add_argument("--model", help="LLM model to use (e.g., gpt-3.5-turbo)")
        parser.add_argument(
            "--private",
            action="store_true",
            help="Use differential privacy (spend epsilon from budget)",
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
            dp_epsilon = 0.05
            dp_delta = delta

        # Build config
        config = GardenerConfig(
            threshold=args.threshold,
            auto_commit=not args.no_commit,
            llm_provider=args.llm if args.llm != "none" else None,
            llm_model=args.model,
            use_dp=use_dp,
            dp_epsilon=dp_epsilon,
            dp_delta=dp_delta,
        )

        # Create gardener
        gardener = Gardener(repo, config)

        # Show status
        episode_count = gardener.get_episode_count()
        print(f"Episodic files: {episode_count}/{config.threshold}")

        if args.dry_run:
            if gardener.should_run() or args.force:
                episodes = gardener.load_episodes()
                clusters = gardener.cluster_episodes(episodes)

                print(f"\nWould process {len(episodes)} episodes into {len(clusters)} clusters:")
                for cluster in clusters:
                    print(f"  - {cluster.topic}: {len(cluster.episodes)} episodes")

                print("\nRun without --dry-run to execute.")
            else:
                print("\nThreshold not met. Use --force to run anyway.")
            return 0

        # Run gardener
        if not gardener.should_run() and not args.force:
            print("\nThreshold not met. Use --force to run anyway.")
            return 0

        print("\nRunning Gardener...")
        result = gardener.run(force=args.force)

        if result.success:
            print(f"\nGardener completed:")
            print(f"  Clusters found: {result.clusters_found}")
            print(f"  Insights generated: {result.insights_generated}")
            print(f"  Episodes archived: {result.episodes_archived}")

            if result.commit_hash:
                print(f"  Commit: {result.commit_hash[:8]}")

            print(f"\n{result.message}")
            return 0
        else:
            print(f"Gardener failed: {result.message}")
            return 1
