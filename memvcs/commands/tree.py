"""
agmem tree - Show working directory or commit tree visually.
"""

import argparse
from pathlib import Path
from typing import Optional

from ..commands.base import require_repo
from ..core.objects import Commit, Tree
from ..core.repository import Repository


def _build_tree_lines(
    base_path: Path,
    prefix: str = "",
    is_last: bool = True,
    show_hidden: bool = False,
    depth_limit: Optional[int] = None,
    current_depth: int = 0,
) -> list[str]:
    """Build tree lines for a directory."""
    lines = []
    if depth_limit is not None and current_depth >= depth_limit:
        return lines
    try:
        entries = sorted(base_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return [f"{prefix}└── [permission denied]"]
    
    if not show_hidden:
        entries = [e for e in entries if not e.name.startswith(".")]
    
    for i, entry in enumerate(entries):
        is_last_entry = i == len(entries) - 1
        connector = "└── " if is_last_entry else "├── "
        lines.append(f"{prefix}{connector}{entry.name}")
        
        if entry.is_dir():
            extension = "    " if is_last_entry else "│   "
            sub_prefix = prefix + extension
            lines.extend(
                _build_tree_lines(
                    entry, sub_prefix, is_last_entry, show_hidden,
                    depth_limit, current_depth + 1
                )
            )
    
    return lines


def _build_tree_from_entries(entries: list) -> list[str]:
    """Build tree lines from commit tree entries (flat path/name/hash)."""
    # Build nested dict: {dir: {subdir: {file: hash}}}
    root: dict = {}
    
    for path, name, hash_id in entries:
        parts = (path.split("/") if path else []) + [name]
        current = root
        for i, part in enumerate(parts):
            is_file = i == len(parts) - 1
            if is_file:
                current[part] = hash_id  # Store hash for files
            else:
                if part not in current:
                    current[part] = {}
                current = current[part]
    
    def _render(node: dict, prefix: str = "") -> list[str]:
        lines = []
        # Directories first, then files; alphabetically within each
        items = sorted(node.items(), key=lambda x: (not isinstance(x[1], dict), x[0].lower()))
        for i, (key, val) in enumerate(items):
            is_last = i == len(items) - 1
            conn = "└── " if is_last else "├── "
            ext = "    " if is_last else "│   "
            if isinstance(val, dict):
                lines.append(f"{prefix}{conn}{key}/")
                lines.extend(_render(val, prefix + ext))
            else:
                lines.append(f"{prefix}{conn}{key} ({val[:8]})")
        return lines
    
    return _render(root)


class TreeCommand:
    """Show directory tree visually."""
    
    name = "tree"
    help = "Show working directory or commit tree visually"
    
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "ref",
            nargs="?",
            default=None,
            help="Commit/branch to show (default: working directory)",
        )
        parser.add_argument(
            "-a", "--all",
            action="store_true",
            help="Show hidden files",
        )
        parser.add_argument(
            "-L", "--depth",
            type=int,
            default=None,
            help="Limit depth of tree",
        )
    
    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        if args.ref:
            # Show tree at commit
            commit_hash = repo.resolve_ref(args.ref)
            if not commit_hash:
                print(f"Error: Unknown revision: {args.ref}")
                return 1
            
            commit = Commit.load(repo.object_store, commit_hash)
            if not commit:
                print(f"Error: Commit not found: {args.ref}")
                return 1
            
            tree = Tree.load(repo.object_store, commit.tree)
            if not tree:
                print(f"Error: Tree not found for {args.ref}")
                return 1
            
            entries = [(e.path, e.name, e.hash) for e in tree.entries]
            
            print(f"📁 {args.ref} ({commit_hash[:8]})")
            print("│")
            for line in _build_tree_from_entries(entries):
                print(line)
        else:
            # Show working directory
            current_dir = repo.current_dir
            if not current_dir.exists():
                print("Error: current/ directory not found.")
                return 1
            
            print(f"📁 current/ (working directory)")
            print("│")
            for line in _build_tree_lines(
                current_dir, "", True, args.all, args.depth, 0
            ):
                print(line)
        
        return 0
