"""
agmem clone - Clone a remote memory repository.
"""

import argparse
import shutil
from pathlib import Path

from memvcs.core.constants import MEMORY_TYPES


class CloneCommand:
    """Clone a remote agmem repository."""

    name = "clone"
    help = "Clone a memory repository from a remote (file:// URL)"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "url",
            help="Remote URL (e.g. file:///path/to/remote-repo)",
        )
        parser.add_argument(
            "directory",
            nargs="?",
            help="Local directory to clone into (default: infer from remote)",
        )

    @staticmethod
    def execute(args) -> int:
        from memvcs.core.remote import parse_remote_url
        from memvcs.core.repository import Repository

        url = args.url
        if not url:
            print("Error: URL required")
            return 1

        try:
            remote_path = parse_remote_url(url)
        except ValueError as e:
            print(f"Error: {e}")
            return 1

        remote_mem = remote_path / ".mem"
        if not remote_mem.exists():
            print(f"Error: Not an agmem repository: {remote_path}")
            return 1

        # Target directory (validate relative paths to avoid path traversal)
        cwd = Path.cwd().resolve()
        if args.directory:
            p = Path(args.directory)
            target = p.resolve()
            if not p.is_absolute():
                try:
                    target.relative_to(cwd)
                except ValueError:
                    print("Error: Target path escapes current directory")
                    return 1
        else:
            target = cwd / remote_path.name

        if target.exists() and any(target.iterdir()):
            print(f"Error: Directory not empty: {target}")
            return 1

        target.mkdir(parents=True, exist_ok=True)

        # Copy .mem and current from remote
        shutil.copytree(remote_mem, target / ".mem")
        remote_current = remote_path / "current"
        if remote_current.exists():
            shutil.copytree(remote_current, target / "current")
        else:
            (target / "current").mkdir(parents=True)
            for mem_type in MEMORY_TYPES:
                (target / "current" / mem_type).mkdir(exist_ok=True)

        # Set remote origin to source
        import json

        config_file = target / ".mem" / "config.json"
        config = json.loads(config_file.read_text()) if config_file.exists() else {}
        if "remotes" not in config:
            config["remotes"] = {}
        config["remotes"]["origin"] = {
            "url": url if url.startswith("file://") else f"file://{remote_path}"
        }
        config_file.write_text(json.dumps(config, indent=2))

        # Copy remote's public key to .mem/keys/remotes/origin.pub for trust store
        remote_keys = remote_mem / "keys" / "public.pem"
        if remote_keys.exists():
            keys_remotes = target / ".mem" / "keys" / "remotes"
            keys_remotes.mkdir(parents=True, exist_ok=True)
            shutil.copy2(remote_keys, keys_remotes / "origin.pub")

        print(f"Cloned into {target}")
        return 0
