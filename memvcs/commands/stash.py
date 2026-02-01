"""
agmem stash - Stash changes for later (Git-like).
"""

import argparse
from pathlib import Path

from ..commands.base import require_repo
from ..core.repository import Repository


class StashCommand:
    """Stash working directory changes."""

    name = "stash"
    help = "Stash changes for later (save work in progress)"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        subparsers = parser.add_subparsers(dest="stash_action", help="Stash action")

        # Default: list (when no subcommand given)
        parser.set_defaults(stash_action="list")

        # stash (push)
        push_p = subparsers.add_parser("push", help="Stash current changes")
        push_p.add_argument("-m", "--message", default="", help="Stash message")

        # stash pop
        subparsers.add_parser("pop", help="Apply and remove most recent stash")

        # stash list (default)
        subparsers.add_parser("list", help="List stashes")

        # stash apply
        apply_p = subparsers.add_parser("apply", help="Apply stash without removing")
        apply_p.add_argument("stash_ref", nargs="?", default="stash@{0}", help="Stash reference")

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        action = getattr(args, "stash_action", None)
        if action is None:
            action = "list"

        if action == "push":
            stash_hash = repo.stash_create(getattr(args, "message", "") or "")
            if stash_hash:
                print(f"Stashed changes (stash@{0})")
                return 0
            else:
                print("No local changes to stash.")
                return 0

        elif action == "pop":
            stash_hash = repo.stash_pop(0)
            if stash_hash:
                print(f"Restored stashed changes")
                return 0
            else:
                print("No stash entries found.")
                return 1

        elif action == "list":
            stashes = repo.refs.stash_list()
            if not stashes:
                print("No stash entries found.")
                return 0
            for i, s in enumerate(stashes):
                msg = s.get("message", "WIP")
                h = s.get("hash", "")[:8]
                print(f"stash@{{{i}}}: {h} {msg}")
            return 0

        elif action == "apply":
            ref = getattr(args, "stash_ref", "stash@{0}")
            commit_hash = repo.resolve_ref(ref)
            if not commit_hash:
                print(f"Error: Stash not found: {ref}")
                return 1
            from ..core.objects import Tree, Blob

            tree = repo.get_commit_tree(commit_hash)
            if tree:
                for entry in tree.entries:
                    blob = Blob.load(repo.object_store, entry.hash)
                    if blob:
                        fp = repo.current_dir / entry.path / entry.name
                        fp.parent.mkdir(parents=True, exist_ok=True)
                        fp.write_bytes(blob.content)
                print("Applied stash (changes in working directory)")
            return 0

        return 1
