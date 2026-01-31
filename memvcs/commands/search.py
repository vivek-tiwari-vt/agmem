"""
agmem search - Semantic search over memory.
"""

import argparse
import sys
from pathlib import Path


def _is_vector_unavailable_error(exc: Exception) -> bool:
    """True if the exception indicates vector deps are missing (fall back to text search)."""
    msg = str(exc).lower()
    return any(
        key in msg for key in ("sqlite-vec", "sentence-transformers", "vector search")
    )


def _first_line_containing(content: str, query: str, max_len: int = 200) -> str:
    """Return the first line that contains query (lowercased), trimmed to max_len, or empty string."""
    for line in content.splitlines():
        if query in line.lower():
            return line.strip()[:max_len]
    return ""


class SearchCommand:
    """Semantic search over memory files."""

    name = "search"
    help = "Search memory (semantic with agmem[vector], else plain text)"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "query",
            nargs="?",
            default="",
            help="Search query for semantic search",
        )
        parser.add_argument(
            "--limit", "-n",
            type=int,
            default=10,
            help="Maximum results to return (default: 10)",
        )
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Rebuild vector index from current/ before searching",
        )
        parser.add_argument(
            "--index-only",
            action="store_true",
            help="Only build/rebuild index, do not search",
        )

    @staticmethod
    def execute(args) -> int:
        from memvcs.commands.base import require_repo
        from memvcs.core.repository import Repository

        repo, code = require_repo()
        if code != 0:
            return code

        try:
            from memvcs.core.vector_store import VectorStore

            store = VectorStore(repo.mem_dir)
        except ImportError:
            return SearchCommand._text_search(repo, args)

        try:
            if args.rebuild or args.index_only:
                count = store.rebuild_index(repo.current_dir)
                print(f"Indexed {count} file(s).")
                if args.index_only:
                    return 0

            # Lazy index on first search if index is empty
            if args.query and not store.db_path.exists():
                print("Building index on first search...")
                count = store.index_directory(repo.current_dir)
                print(f"Indexed {count} file(s).\n")

            if not args.query:
                if not args.index_only:
                    print("Usage: agmem search <query> [--limit N] [--rebuild]")
                return 0

            results = store.search(args.query, limit=args.limit)

            if not results:
                print(f"No results for '{args.query}'.")
                print("Try --rebuild to index current/ files.")
                return 0

            for path, snippet, distance in results:
                print(f"\n--- {path} (distance: {distance:.4f}) ---")
                print(snippet)
                print()

            return 0
        except Exception as e:
            if _is_vector_unavailable_error(e):
                return SearchCommand._text_search(repo, args)
            print(f"Error: {e}", file=sys.stderr)
            return 1
        finally:
            store.close()

    @staticmethod
    def _text_search(repo, args) -> int:
        """Plain text search when vector store is not available."""
        if args.index_only or args.rebuild:
            print("Note: Install agmem[vector] for index/rebuild. Using plain text search.")
        if not args.query:
            print("Usage: agmem search <query> [--limit N]")
            return 0

        query_lower = args.query.lower()
        results = []
        current_dir = repo.current_dir
        if not current_dir.exists():
            print("No current/ directory.")
            return 0

        for ext in ("*.md", "*.txt"):
            for f in current_dir.rglob(ext):
                if not f.is_file():
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                if query_lower not in content.lower():
                    continue
                try:
                    rel = str(f.relative_to(current_dir))
                except ValueError:
                    continue
                # Snippet: line containing query
                for line in content.splitlines():
                    if query_lower in line.lower():
                        snippet = line.strip()[:200]
                        break
                else:
                    snippet = content[:200].strip()
                results.append((rel, snippet, 0.0))
                if len(results) >= args.limit:
                    break
            if len(results) >= args.limit:
                break

        if not results:
            print(f"No results for '{args.query}'.")
            return 0

        for path, snippet, _ in results:
            print(f"\n--- {path} ---")
            print(snippet)
            print()
        return 0
