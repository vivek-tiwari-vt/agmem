"""
agmem resolve - Structured conflict resolution.

Resolve merge conflicts with ours/theirs/both choices; record in audit.
"""

import argparse
import json
from pathlib import Path
from typing import Optional

from ..commands.base import require_repo


def _path_under_current(path_str: str, current_dir: Path) -> Optional[Path]:
    """Resolve path under current_dir; return None if it escapes (path traversal)."""
    try:
        full = (current_dir / path_str).resolve()
        full.relative_to(current_dir.resolve())
        return full
    except (ValueError, RuntimeError):
        return None


def _resolved_content(choice: str, ours: str, theirs: str) -> str:
    """Return content for choice: ours, theirs, or both (merged)."""
    if choice == "ours":
        return ours
    if choice == "theirs":
        return theirs
    return ours.rstrip() + "\n\n--- merged ---\n\n" + theirs


class ResolveCommand:
    """Resolve merge conflicts interactively (ours/theirs/both)."""

    name = "resolve"
    help = "Resolve merge conflicts (ours / theirs / both)"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "path",
            nargs="?",
            help="Conflict path to resolve (or resolve all if omitted)",
        )
        parser.add_argument(
            "--ours",
            action="store_true",
            help="Resolve with our version",
        )
        parser.add_argument(
            "--theirs",
            action="store_true",
            help="Resolve with their version",
        )
        parser.add_argument(
            "--both",
            action="store_true",
            help="Keep both (append theirs after ours with separator)",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        merge_dir = repo.mem_dir / "merge"
        conflicts_file = merge_dir / "conflicts.json"
        if not conflicts_file.exists():
            print("No unresolved conflicts.")
            return 0

        try:
            conflicts = json.loads(conflicts_file.read_text())
        except Exception:
            print("Could not read conflicts file.")
            return 1

        if not conflicts:
            print("No unresolved conflicts.")
            conflicts_file.unlink(missing_ok=True)
            return 0

        choice = None
        if args.ours:
            choice = "ours"
        elif args.theirs:
            choice = "theirs"
        elif args.both:
            choice = "both"

        resolved = 0
        remaining = []
        for c in conflicts:
            path = c.get("path", "")
            if args.path and path != args.path:
                remaining.append(c)
                continue
            if choice is None:
                print(f"Conflict: {path}")
                print("  Use: agmem resolve <path> --ours | --theirs | --both")
                remaining.append(c)
                continue
            ours_content = c.get("ours_content") or ""
            theirs_content = c.get("theirs_content") or ""
            full_path = _path_under_current(path, repo.current_dir)
            if full_path is None:
                print(f"Error: Conflict path escapes repository: {path}")
                remaining.append(c)
                continue
            content = _resolved_content(choice, ours_content, theirs_content)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            resolved += 1
            try:
                from ..core.audit import append_audit

                append_audit(repo.mem_dir, "resolve", {"path": path, "choice": choice})
            except Exception:
                pass

        if remaining:
            conflicts_file.write_text(json.dumps(remaining, indent=2))
        else:
            conflicts_file.unlink(missing_ok=True)
        if resolved:
            print(f"Resolved {resolved} conflict(s). Stage and commit to complete.")
        return 0
