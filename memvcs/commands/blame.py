"""
agmem blame - Show who changed each line (Git-like) or trace semantic facts.
"""

import argparse
from pathlib import Path

from ..commands.base import require_repo
from ..core.repository import Repository
from ..core.objects import Commit, Tree, Blob


class BlameCommand:
    """Show author and commit for each line of a file, or trace semantic facts."""

    name = "blame"
    help = "Show who changed each line of a memory file, or trace semantic facts"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument("file", nargs="?", help="File to blame (path relative to current/)")
        parser.add_argument(
            "ref", nargs="?", default="HEAD", help="Commit to blame at (default: HEAD)"
        )
        parser.add_argument(
            "--query", "-q", help='Semantic query to trace (e.g., "Why does agent think X?")'
        )
        parser.add_argument(
            "--limit",
            "-n",
            type=int,
            default=5,
            help="Number of results to show for semantic blame (default: 5)",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        # Semantic blame mode
        if args.query:
            return BlameCommand._semantic_blame(repo, args.query, args.limit)

        # File blame mode
        if not args.file:
            print("Error: Either --query or a file path is required.")
            print("Usage: agmem blame <file> [ref]")
            print('       agmem blame --query "Why does agent think X?"')
            return 1

        return BlameCommand._file_blame(repo, args.file, args.ref)

    @staticmethod
    def _file_blame(repo, filepath: str, ref: str) -> int:
        """Traditional file-based blame."""
        commit_hash = repo.resolve_ref(ref)
        if not commit_hash:
            print(f"Error: Unknown revision: {ref}")
            return 1

        # Get file content at commit
        tree = repo.get_commit_tree(commit_hash)
        if not tree:
            print("Error: Could not load tree.")
            return 1

        # Find file in tree (support path like semantic/user-prefs.md)
        blob_hash = None
        for entry in tree.entries:
            path = entry.path + "/" + entry.name if entry.path else entry.name
            if path == filepath:
                blob_hash = entry.hash
                break

        if not blob_hash:
            print(f"Error: File not found in {ref}: {filepath}")
            return 1

        blob = Blob.load(repo.object_store, blob_hash)
        if not blob:
            print("Error: Could not load file content.")
            return 1

        lines = blob.content.decode("utf-8", errors="replace").splitlines()
        commit = Commit.load(repo.object_store, commit_hash)
        author_short = commit.author.split("<")[0].strip()[:20] if commit else "unknown"
        hash_short = commit_hash[:8]

        for i, line in enumerate(lines, 1):
            print(f"{hash_short} ({author_short:20} {i:4}) {line}")

        return 0

    @staticmethod
    def _semantic_blame(repo, query: str, limit: int) -> int:
        """
        Semantic blame - trace which commit introduced a fact.

        Searches the vector store and shows provenance for matching chunks.
        """
        try:
            from ..core.vector_store import VectorStore
        except ImportError:
            print("Error: Vector search requires sqlite-vec.")
            print("Install with: pip install agmem[vector]")
            return 1

        try:
            vs = VectorStore(repo.root / ".mem")
            results = vs.search_with_provenance(query, limit=limit)
        except Exception as e:
            print(f"Error: Vector search failed: {e}")
            print("Try running 'agmem search --rebuild' to rebuild the index.")
            return 1

        if not results:
            print("No matching facts found in memory.")
            print("Try rebuilding the index with 'agmem search --rebuild'")
            return 0

        print(f'Semantic blame for: "{query}"')
        print("=" * 60)

        for i, result in enumerate(results, 1):
            path = result["path"]
            content = result["content"]
            similarity = result["similarity"]
            commit_hash = result["commit_hash"]
            author = result["author"]
            indexed_at = result["indexed_at"]

            print(f"\n[{i}] {path}")
            print(f"    Similarity: {similarity:.2%}")

            if commit_hash:
                # Try to get commit details
                commit = Commit.load(repo.object_store, commit_hash)
                if commit:
                    print(f"    Commit: {commit_hash[:8]}")
                    print(f"    Author: {commit.author}")
                    print(f"    Date: {commit.timestamp}")
                    print(f"    Message: {commit.message}")
                else:
                    print(f"    Commit: {commit_hash[:8]} (details unavailable)")
                    if author:
                        print(f"    Author: {author}")
            else:
                print("    Commit: (not tracked)")
                if indexed_at:
                    print(f"    Indexed: {indexed_at}")

            # Show content preview
            print(f"\n    Content preview:")
            for line in content.split("\n")[:5]:
                print(f"      {line[:70]}")
            if len(content.split("\n")) > 5:
                print("      ...")

        print()
        return 0
