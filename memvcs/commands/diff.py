"""
agmem diff - Show changes between commits, commit and working tree, etc.
"""

import argparse
import os
from pathlib import Path

from ..commands.base import require_repo
from ..core.diff import DiffEngine
from ..core.repository import Repository


class DiffCommand:
    """Show differences between commits."""
    
    name = 'diff'
    help = 'Show changes between commits, commit and working tree, etc.'
    
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            'ref1',
            nargs='?',
            help='First commit/branch to compare'
        )
        parser.add_argument(
            'ref2',
            nargs='?',
            help='Second commit/branch to compare'
        )
        parser.add_argument(
            '--cached', '--staged',
            action='store_true',
            help='Show changes staged for commit'
        )
        parser.add_argument(
            '--stat',
            action='store_true',
            help='Show diffstat instead of full diff'
        )
    
    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        engine = DiffEngine(repo.object_store)
        
        # Determine what to diff
        if args.cached:
            # Diff staged changes against HEAD
            head_commit = repo.get_head_commit()
            if not head_commit:
                print("No commits yet. Nothing to diff.")
                return 0
            
            staged_files = repo.staging.get_staged_files()
            if not staged_files:
                print("No staged changes.")
                return 0
            
            # Get staged content
            working_files = {}
            for path, sf in staged_files.items():
                from ..core.objects import Blob
                blob = Blob.load(repo.object_store, sf.blob_hash)
                if blob:
                    working_files[path] = blob.content
            
            tree_diff = engine.diff_working_dir(
                head_commit.store(repo.object_store),
                working_files
            )
            
            print(engine.format_diff(tree_diff, 'HEAD', 'staged'))
            return 0
        
        # Diff between two refs
        if args.ref1 and args.ref2:
            commit1 = repo.resolve_ref(args.ref1)
            commit2 = repo.resolve_ref(args.ref2)
            
            if not commit1:
                print(f"Error: Unknown revision: {args.ref1}")
                return 1
            if not commit2:
                print(f"Error: Unknown revision: {args.ref2}")
                return 1
            
            tree_diff = engine.diff_commits(commit1, commit2)
            
            if args.stat:
                print(f" {tree_diff.added_count} file(s) added")
                print(f" {tree_diff.deleted_count} file(s) deleted")
                print(f" {tree_diff.modified_count} file(s) modified")
            else:
                print(engine.format_diff(tree_diff, args.ref1, args.ref2))
            
            return 0
        
        # Diff working tree against a ref
        if args.ref1:
            commit_hash = repo.resolve_ref(args.ref1)
            if not commit_hash:
                print(f"Error: Unknown revision: {args.ref1}")
                return 1
            
            # Get working directory files
            working_files = {}
            for root, dirs, files in os.walk(repo.current_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for filename in files:
                    full_path = Path(root) / filename
                    rel_path = str(full_path.relative_to(repo.current_dir))
                    working_files[rel_path] = full_path.read_bytes()
            
            tree_diff = engine.diff_working_dir(commit_hash, working_files)
            
            if args.stat:
                print(f" {tree_diff.added_count} file(s) added")
                print(f" {tree_diff.deleted_count} file(s) deleted")
                print(f" {tree_diff.modified_count} file(s) modified")
            else:
                print(engine.format_diff(tree_diff, args.ref1, 'working'))
            
            return 0
        
        # Default: diff working tree against HEAD
        head_commit = repo.get_head_commit()
        if not head_commit:
            print("No commits yet. Nothing to diff.")
            return 0
        
        # Get working directory files
        working_files = {}
        for root, dirs, files in os.walk(repo.current_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for filename in files:
                full_path = Path(root) / filename
                rel_path = str(full_path.relative_to(repo.current_dir))
                working_files[rel_path] = full_path.read_bytes()
        
        tree_diff = engine.diff_working_dir(
            head_commit.store(repo.object_store),
            working_files
        )
        
        if args.stat:
            print(f" {tree_diff.added_count} file(s) added")
            print(f" {tree_diff.deleted_count} file(s) deleted")
            print(f" {tree_diff.modified_count} file(s) modified")
        else:
            print(engine.format_diff(tree_diff, 'HEAD', 'working'))
        
        return 0
