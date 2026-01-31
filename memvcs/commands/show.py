"""
agmem show - Show various types of objects.
"""

import argparse
import json
from pathlib import Path

from ..commands.base import require_repo
from ..core.objects import Blob, Commit, Tree
from ..core.repository import Repository


class ShowCommand:
    """Show various types of objects."""
    
    name = 'show'
    help = 'Show various types of objects'
    
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            'object',
            help='Object to show (commit, tree, blob, branch)'
        )
        parser.add_argument(
            '--type', '-t',
            choices=['commit', 'tree', 'blob', 'auto'],
            default='auto',
            help='Type of object to show'
        )
        parser.add_argument(
            '--raw',
            action='store_true',
            help='Show raw object content'
        )
    
    @staticmethod
    def execute(args) -> int:
        # Find repository
        repo, code = require_repo()
        if code != 0:
            return code

        
        obj_ref = args.object
        obj_hash = None
        obj_type = args.type
        
        # Try to resolve as reference
        resolved = repo.resolve_ref(obj_ref)
        if resolved:
            obj_hash = resolved
        else:
            # Assume it's a hash
            obj_hash = obj_ref
        
        # Try to determine type if auto
        if obj_type == 'auto':
            # Try commit first
            commit = Commit.load(repo.object_store, obj_hash)
            if commit:
                obj_type = 'commit'
            else:
                # Try tree
                tree = Tree.load(repo.object_store, obj_hash)
                if tree:
                    obj_type = 'tree'
                else:
                    # Try blob
                    blob = Blob.load(repo.object_store, obj_hash)
                    if blob:
                        obj_type = 'blob'
                    else:
                        print(f"Error: Object not found: {obj_ref}")
                        return 1
        
        # Display based on type
        if obj_type == 'commit':
            commit = Commit.load(repo.object_store, obj_hash)
            if not commit:
                print(f"Error: Commit not found: {obj_ref}")
                return 1
            
            print(f"commit {obj_hash}")
            print(f"Author: {commit.author}")
            print(f"Date:   {commit.timestamp}")
            print()
            print(f"    {commit.message}")
            print()
            print(f"tree {commit.tree}")
            if commit.parents:
                print(f"parent {' '.join(commit.parents)}")
        
        elif obj_type == 'tree':
            tree = Tree.load(repo.object_store, obj_hash)
            if not tree:
                print(f"Error: Tree not found: {obj_ref}")
                return 1
            
            print(f"tree {obj_hash}")
            print()
            for entry in sorted(tree.entries, key=lambda e: e.name):
                path = entry.path + '/' + entry.name if entry.path else entry.name
                print(f"{entry.mode} {entry.type} {entry.hash[:8]}\t{path}")
        
        elif obj_type == 'blob':
            blob = Blob.load(repo.object_store, obj_hash)
            if not blob:
                print(f"Error: Blob not found: {obj_ref}")
                return 1
            
            if args.raw:
                print(blob.content.decode('utf-8', errors='replace'))
            else:
                print(f"blob {obj_hash}")
                print(f"Size: {len(blob.content)} bytes")
                print()
                content = blob.content.decode('utf-8', errors='replace')
                if len(content) > 1000:
                    print(content[:1000] + "\n... (truncated)")
                else:
                    print(content)
        
        return 0
