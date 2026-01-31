"""
agmem merge - Join two or more development histories together.
"""

import argparse

from ..commands.base import require_repo
from ..core.merge import MergeEngine
from ..core.repository import Repository


class MergeCommand:
    """Merge branches."""
    
    name = 'merge'
    help = 'Join two or more development histories together'
    
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            'branch',
            help='Branch to merge into current branch'
        )
        parser.add_argument(
            '-m', '--message',
            help='Merge commit message'
        )
        parser.add_argument(
            '--no-commit',
            action='store_true',
            help='Perform merge but do not commit'
        )
        parser.add_argument(
            '--abort',
            action='store_true',
            help='Abort the current merge'
        )
    
    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        # Abort merge
        if args.abort:
            # TODO: Implement merge abort
            print("Merge abort not yet implemented")
            return 0
        
        # Check if we're on a branch
        current_branch = repo.refs.get_current_branch()
        if not current_branch:
            print("Error: Not currently on any branch.")
            print("Cannot merge when HEAD is detached.")
            return 1
        
        # Check if trying to merge current branch
        if args.branch == current_branch:
            print(f"Error: Cannot merge '{args.branch}' into itself")
            return 1
        
        # Check if branch exists
        if not repo.refs.branch_exists(args.branch):
            print(f"Error: Branch '{args.branch}' not found.")
            return 1
        
        # Perform merge
        engine = MergeEngine(repo)
        result = engine.merge(args.branch, message=args.message)
        
        if result.success:
            print(f"Merge successful: {result.message}")
            if result.commit_hash:
                print(f"  Commit: {result.commit_hash[:8]}")
            return 0
        else:
            print(f"Merge failed: {result.message}")
            
            if result.conflicts:
                print()
                print("Conflicts:")
                for conflict in result.conflicts:
                    print(f"  {conflict.path}")
                print()
                print("Resolve conflicts and run 'agmem commit' to complete the merge.")
            
            return 1
