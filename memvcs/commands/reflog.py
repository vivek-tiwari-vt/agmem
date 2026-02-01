"""
agmem reflog - Show reference history (Git-like).
"""

import argparse
from pathlib import Path

from ..commands.base import require_repo
from ..core.repository import Repository


class ReflogCommand:
    """Show reflog - history of HEAD changes."""

    name = "reflog"
    help = "Show reference log (history of HEAD changes)"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument("ref", nargs="?", default="HEAD", help="Reference to show log for")
        parser.add_argument(
            "-n", "--max-count", type=int, default=20, help="Maximum number of entries"
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        entries = repo.refs.get_reflog(args.ref, args.max_count)

        if not entries:
            print("No reflog entries found.")
            return 0

        for e in entries:
            h = e["hash"][:8]
            ts = e.get("timestamp", "")[:19]
            msg = e.get("message", "")
            print(f"{h} {ts} {msg}")

        return 0
