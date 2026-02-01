"""
agmem gc - Garbage collection.

Remove unreachable objects; optionally repack.
"""

import argparse

from ..commands.base import require_repo
from ..core.pack import run_gc, run_repack


class GcCommand:
    """Garbage collect unreachable objects."""

    name = "gc"
    help = "Remove unreachable objects (garbage collection)"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be removed without deleting",
        )
        parser.add_argument(
            "--prune-days",
            type=int,
            default=90,
            metavar="N",
            help="Consider reflog entries within N days (default 90)",
        )
        parser.add_argument(
            "--repack",
            action="store_true",
            help="After GC, pack reachable loose objects into a pack file",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        gc_prune_days = getattr(args, "prune_days", 90)
        deleted, freed = run_gc(
            repo.mem_dir,
            repo.object_store,
            gc_prune_days=gc_prune_days,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            print(f"Would remove {deleted} unreachable object(s) ({freed} bytes).")
        else:
            print(f"Removed {deleted} unreachable object(s) ({freed} bytes reclaimed).")

        if getattr(args, "repack", False) and not args.dry_run:
            packed, repack_freed = run_repack(
                repo.mem_dir,
                repo.object_store,
                gc_prune_days=gc_prune_days,
                dry_run=False,
            )
            if packed > 0:
                print(f"Packed {packed} object(s) into pack file ({repack_freed} bytes from loose).")
        return 0
