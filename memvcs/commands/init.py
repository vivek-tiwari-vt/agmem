"""
agmem init - Initialize a new memory repository.
"""

import argparse
from pathlib import Path

from ..core.repository import Repository


class InitCommand:
    """Initialize a new agmem repository."""
    
    name = 'init'
    help = 'Initialize a new memory repository'
    
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            'path',
            nargs='?',
            default='.',
            help='Directory to initialize repository in (default: current directory)'
        )
        parser.add_argument(
            '--author-name',
            default='Agent',
            help='Default author name'
        )
        parser.add_argument(
            '--author-email',
            default='agent@example.com',
            help='Default author email'
        )
    
    @staticmethod
    def execute(args) -> int:
        path = Path(args.path).resolve()
        
        try:
            repo = Repository.init(
                path=path,
                author_name=args.author_name,
                author_email=args.author_email
            )
            
            print(f"Initialized empty agmem repository in {repo.mem_dir}")
            print(f"Author: {args.author_name} <{args.author_email}>")
            print(f"\nNext steps:")
            print(f"  1. Add memory files to {repo.current_dir}/")
            print(f"  2. Run 'agmem add <file>' to stage changes")
            print(f"  3. Run 'agmem commit -m \"message\"' to save snapshot")
            
            return 0
        
        except ValueError as e:
            print(f"Error: {e}")
            return 1
        except Exception as e:
            print(f"Error initializing repository: {e}")
            return 1
