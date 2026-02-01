"""
agmem federated - Federated memory collaboration.

Push local summaries to coordinator; pull merged summaries.
"""

import argparse

from ..commands.base import require_repo
from ..core.federated import get_federated_config, produce_local_summary, push_updates, pull_merged


class FederatedCommand:
    """Federated memory collaboration with coordinator."""

    name = "federated"
    help = "Push/pull federated summaries (coordinator must be configured)"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "action",
            choices=["push", "pull"],
            help="Push local summary or pull merged from coordinator",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        cfg = get_federated_config(repo.root)
        if not cfg:
            print(
                "Federated collaboration not enabled. Set federated.enabled and coordinator_url in config."
            )
            return 1

        if args.action == "push":
            summary = produce_local_summary(
                repo.root,
                cfg["memory_types"],
                use_dp=cfg.get("use_dp", False),
                dp_epsilon=cfg.get("dp_epsilon") or 0.1,
                dp_delta=cfg.get("dp_delta") or 1e-5,
            )
            msg = push_updates(repo.root, summary)
            print(msg)
            return 0 if "Pushed" in msg else 1
        else:
            data = pull_merged(repo.root)
            if data is None:
                print("Pull failed or coordinator unavailable.")
                return 1
            print("Merged summary from coordinator:")
            for k, v in (data or {}).items():
                print(f"  {k}: {v}")
            return 0
