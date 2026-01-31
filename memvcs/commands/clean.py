"""
agmem clean - Remove untracked files (Git-like).
"""

import argparse
import os
from pathlib import Path

from ..commands.base import require_repo
from ..core.repository import Repository


class CleanCommand:
    """Remove untracked files from working directory."""
    
    name = 'clean'
    help = 'Remove untracked files from working directory'
    
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            '-n', '--dry-run',
            action='store_true',
            help='Show what would be removed without removing'
        )
        parser.add_argument(
            '-f', '--force',
            action='store_true',
            help='Required to actually remove files'
        )
        parser.add_argument(
            '-d',
            action='store_true',
            help='Remove untracked directories too'
        )
    
    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        
        status = repo.get_status()
        untracked = status.get('untracked', [])
        
        if not untracked:
            print("Nothing to clean.")
            return 0
        
        if args.dry_run:
            print("Would remove:")
            for p in untracked:
                print(f"  {p}")
            return 0
        
        if not args.force:
            print("Use -f to force removal of untracked files.")
            return 1
        
        removed = 0
        for rel_path in untracked:
            full_path = repo.current_dir / rel_path
            if full_path.exists():
                if full_path.is_file():
                    full_path.unlink()
                    removed += 1
                    print(f"Removed {rel_path}")
                elif args.d and full_path.is_dir():
                    import shutil
                    shutil.rmtree(full_path)
                    removed += 1
                    print(f"Removed {rel_path}/")
        
        print(f"Removed {removed} file(s)")
        return 0
