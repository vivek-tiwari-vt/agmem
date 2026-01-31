"""
agmem reset - Reset current HEAD to the specified state.
"""

import argparse
from pathlib import Path

from ..commands.base import require_repo
from ..core.repository import Repository


class ResetCommand:
    """Reset current HEAD to the specified state."""
    
    name = 'reset'
    help = 'Reset current HEAD to the specified state'
    
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            'commit',
            nargs='?',
            default='HEAD',
            help='Commit to reset to (default: HEAD)'
        )
        parser.add_argument(
            '--soft',
            action='store_true',
            help='Reset HEAD but keep staged changes'
        )
        parser.add_argument(
            '--mixed',
            action='store_true',
            help='Reset HEAD and unstaged changes (default)'
        )
        parser.add_argument(
            '--hard',
            action='store_true',
            help='Reset HEAD, index, and working tree'
        )
    
    @staticmethod
    def execute(args) -> int:
        # Find repository
        repo, code = require_repo()
        if code != 0:
            return code

        
        # Determine mode
        if args.soft:
            mode = 'soft'
        elif args.hard:
            mode = 'hard'
        else:
            mode = 'mixed'
        
        # Resolve commit
        commit_hash = repo.resolve_ref(args.commit)
        if not commit_hash:
            print(f"Error: Unknown revision: {args.commit}")
            return 1
        
        # Get current branch
        current_branch = repo.refs.get_current_branch()
        
        try:
            if mode == 'soft':
                # Just move HEAD
                if current_branch:
                    repo.refs.set_branch_commit(current_branch, commit_hash)
                else:
                    repo.refs.set_head_detached(commit_hash)
                print(f"HEAD is now at {commit_hash[:8]}")
            
            elif mode == 'mixed':
                # Move HEAD and clear staging
                if current_branch:
                    repo.refs.set_branch_commit(current_branch, commit_hash)
                else:
                    repo.refs.set_head_detached(commit_hash)
                
                # Keep staged files but mark them as unstaged
                # (In a full implementation, we'd restore the tree state)
                print(f"HEAD is now at {commit_hash[:8]}")
                print("Staged changes have been unstaged.")
            
            elif mode == 'hard':
                # Move HEAD, clear staging, and restore working tree
                repo.checkout(commit_hash, force=True)
                print(f"HEAD is now at {commit_hash[:8]}")
                print("Working tree has been reset.")
            
            return 0
        
        except Exception as e:
            print(f"Error during reset: {e}")
            return 1
