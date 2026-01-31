"""
agmem log - Show commit history.
"""

import argparse
from datetime import datetime

from ..commands.base import require_repo
from ..core.repository import Repository


class LogCommand:
    """Show commit history."""
    
    name = 'log'
    help = 'Show commit history'
    
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            '--max-count', '-n',
            type=int,
            default=10,
            help='Maximum number of commits to show'
        )
        parser.add_argument(
            '--oneline',
            action='store_true',
            help='Show one commit per line'
        )
        parser.add_argument(
            '--graph',
            action='store_true',
            help='Show ASCII graph of branch/merge history'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Show all branches'
        )
        parser.add_argument(
            'ref',
            nargs='?',
            help='Start from this reference (branch, tag, or commit)'
        )
    
    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        # Get commits
        commits = repo.get_log(max_count=args.max_count)
        
        if not commits:
            print("No commits yet.")
            return 0
        
        if args.oneline:
            for commit in commits:
                print(f"{commit['short_hash']} {commit['message']}")
        elif args.graph:
            # Simple ASCII graph
            for i, commit in enumerate(commits):
                prefix = "* " if i == 0 else "| "
                print(f"{prefix}{commit['short_hash']} {commit['message']}")
                if i < len(commits) - 1:
                    print("|")
        else:
            for i, commit in enumerate(commits):
                if i > 0:
                    print()
                
                # Commit header
                print(f"\033[33mcommit {commit['hash']}\033[0m")
                
                # Show branch info if this is HEAD
                head = repo.refs.get_head()
                if head['type'] == 'branch':
                    head_commit = repo.refs.get_branch_commit(head['value'])
                    if head_commit == commit['hash']:
                        print(f"\033[36mHEAD -> {head['value']}\033[0m")
                
                # Author and date
                print(f"Author: {commit['author']}")
                
                # Format timestamp
                try:
                    ts = commit['timestamp']
                    if ts.endswith('Z'):
                        ts = ts[:-1]
                    dt = datetime.fromisoformat(ts)
                    date_str = dt.strftime('%a %b %d %H:%M:%S %Y')
                    print(f"Date:   {date_str}")
                except:
                    print(f"Date:   {commit['timestamp']}")
                
                # Message
                print()
                print(f"    {commit['message']}")
        
        return 0
