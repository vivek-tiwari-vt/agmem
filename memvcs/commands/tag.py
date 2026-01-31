"""
agmem tag - Create, list, delete or verify a tag.
"""

import argparse
from datetime import datetime
from pathlib import Path

from ..commands.base import require_repo
from ..core.objects import Tag
from ..core.repository import Repository


class TagCommand:
    """Manage tags."""
    
    name = 'tag'
    help = 'Create, list, delete or verify a tag'
    
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            'name',
            nargs='?',
            help='Tag name'
        )
        parser.add_argument(
            'commit',
            nargs='?',
            help='Commit to tag (default: HEAD)'
        )
        parser.add_argument(
            '--list', '-l',
            action='store_true',
            help='List tags'
        )
        parser.add_argument(
            '--delete', '-d',
            action='store_true',
            help='Delete a tag'
        )
        parser.add_argument(
            '-m', '--message',
            help='Tag message'
        )
        parser.add_argument(
            '--force', '-f',
            action='store_true',
            help='Force replace existing tag'
        )
    
    @staticmethod
    def execute(args) -> int:
        # Find repository
        repo, code = require_repo()
        if code != 0:
            return code

        
        # List tags
        if args.list or (not args.name and not args.delete):
            tags = repo.refs.list_tags()
            
            if not tags:
                print("No tags yet.")
                return 0
            
            for tag in sorted(tags):
                commit_hash = repo.refs.get_tag_commit(tag)
                short_hash = commit_hash[:8] if commit_hash else "????????"
                print(f"{tag}\t{short_hash}")
            
            return 0
        
        # Delete tag
        if args.delete:
            if not args.name:
                print("Error: Tag name required for deletion")
                return 1
            
            if repo.refs.delete_tag(args.name):
                print(f"Deleted tag '{args.name}'")
                return 0
            else:
                print(f"Error: Tag '{args.name}' not found")
                return 1
        
        # Create tag
        if args.name:
            # Check if tag exists
            if repo.refs.tag_exists(args.name) and not args.force:
                print(f"Error: Tag '{args.name}' already exists")
                print("Use -f to force replace")
                return 1
            
            # Get commit to tag
            commit_ref = args.commit or 'HEAD'
            commit_hash = repo.resolve_ref(commit_ref)
            
            if not commit_hash:
                print(f"Error: Unknown revision: {commit_ref}")
                return 1
            
            # Delete existing tag if forcing
            if args.force and repo.refs.tag_exists(args.name):
                repo.refs.delete_tag(args.name)
            
            # Create tag
            message = args.message or f"Tag {args.name}"
            if repo.refs.create_tag(args.name, commit_hash, message):
                print(f"Created tag '{args.name}' at {commit_hash[:8]}")
                return 0
            else:
                print(f"Error: Could not create tag '{args.name}'")
                return 1
        
        return 0
