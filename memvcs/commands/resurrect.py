"""
agmem resurrect - Restore archived (decayed) memories.
"""

import argparse
import shutil
from pathlib import Path

from ..commands.base import require_repo


class ResurrectCommand:
    """Restore memories from .mem/forgetting/."""

    name = "resurrect"
    help = "Restore archived (decayed) memories from forgetting/"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "path",
            nargs="?",
            help="Path or pattern to restore (e.g., semantic/user-prefs.md)",
        )
        parser.add_argument(
            "--list",
            "-l",
            action="store_true",
            help="List archived memories",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        forgetting_dir = repo.mem_dir / "forgetting"
        if not forgetting_dir.exists():
            print("No forgotten memories found.")
            return 0

        if args.list:
            for sub in sorted(forgetting_dir.iterdir()):
                if sub.is_dir():
                    print(f"\n{sub.name}:")
                    for f in sorted(sub.glob("*")):
                        if f.is_file():
                            print(f"  - {f.name}")
            return 0

        if not args.path:
            print("Error: Path to restore is required.")
            print("Usage: agmem resurrect <path>")
            print("       agmem resurrect --list")
            return 1

        # Find archived file
        pattern = args.path.replace("/", "_")
        found = []
        for sub in forgetting_dir.iterdir():
            if sub.is_dir():
                for f in sub.glob("*"):
                    if f.is_file() and (pattern in f.name or f.name == args.path):
                        found.append(f)

        if not found:
            print(f"No archived memory matching '{args.path}' found.")
            print("Use 'agmem resurrect --list' to see available archives.")
            return 1

        for archived in found:
            # Restore to current/
            orig_path = (
                archived.name.replace("_", "/", 1) if "_" in archived.name else archived.name
            )
            dest = repo.current_dir / orig_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(archived), str(dest))
            print(f"Restored {archived.name} -> {orig_path}")

        return 0
