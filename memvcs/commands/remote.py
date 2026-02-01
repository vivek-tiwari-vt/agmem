"""
agmem remote - Manage remote URLs.
"""

import argparse
from pathlib import Path


class RemoteCommand:
    """Manage remote repository URLs."""

    name = "remote"
    help = "Manage remote URLs (add, set-url, show)"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        subparsers = parser.add_subparsers(dest="remote_action", required=True)
        add_p = subparsers.add_parser("add", help="Add a remote")
        add_p.add_argument("name", help="Remote name (e.g. origin)")
        add_p.add_argument("url", help="Remote URL (e.g. file:///path)")
        set_p = subparsers.add_parser("set-url", help="Set remote URL")
        set_p.add_argument("name", help="Remote name")
        set_p.add_argument("url", help="New URL")
        subparsers.add_parser("show", help="Show remotes")

    @staticmethod
    def execute(args) -> int:
        from memvcs.commands.base import require_repo
        from memvcs.core.remote import Remote

        repo, code = require_repo()
        if code != 0:
            return code

        remote = Remote(repo.root, getattr(args, "name", "origin"))

        if args.remote_action == "add" or args.remote_action == "set-url":
            r = Remote(repo.root, args.name)
            r.set_remote_url(args.url)
            print(f"Remote '{args.name}' set to {args.url}")
        elif args.remote_action == "show":
            import json

            config = json.loads((repo.root / ".mem" / "config.json").read_text())
            remotes = config.get("remotes", {})
            if remotes:
                for name, info in remotes.items():
                    print(f"{name}\t{info.get('url', '')}")
            else:
                print("No remotes configured.")

        return 0
