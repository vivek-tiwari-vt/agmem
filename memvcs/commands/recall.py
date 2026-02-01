"""
agmem recall - Context-aware retrieval with pluggable strategies.
"""

import argparse
import json
import sys
from pathlib import Path

from ..commands.base import require_repo
from ..core.access_index import AccessIndex
from ..retrieval import RecallEngine


def _is_vector_unavailable_error(exc: Exception) -> bool:
    """True if exception indicates vector deps are missing."""
    msg = str(exc).lower()
    return any(
        key in msg
        for key in ("sqlite-vec", "sentence-transformers", "vector search", "agmem[vector]")
    )


class RecallCommand:
    """Context-aware recall with pluggable strategies."""

    name = "recall"
    help = "Recall curated memories for the current task (context-aware retrieval)"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "--context",
            "-c",
            default="",
            help="Current task description (used for embedding similarity)",
        )
        parser.add_argument(
            "--strategy",
            "-s",
            choices=["recency", "importance", "similarity", "hybrid"],
            default="hybrid",
            help="Recall strategy (default: hybrid)",
        )
        parser.add_argument(
            "--limit",
            "-n",
            type=int,
            default=10,
            help="Max chunks to return (default: 10)",
        )
        parser.add_argument(
            "--exclude",
            "-e",
            action="append",
            default=[],
            help="Tags/paths to exclude (e.g., experiment/*); repeatable",
        )
        parser.add_argument(
            "--no-cache",
            action="store_true",
            help="Disable recall cache",
        )
        parser.add_argument(
            "--format",
            "-f",
            choices=["json", "text"],
            default="json",
            help="Output format (default: json)",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        vector_store = None
        try:
            from ..core.vector_store import VectorStore

            vector_store = VectorStore(repo.mem_dir)
        except ImportError:
            if args.strategy in ("similarity", "hybrid"):
                print(
                    "Error: Strategy '{}' requires agmem[vector]. "
                    "Install with: pip install agmem[vector]".format(args.strategy),
                    file=sys.stderr,
                )
                return 1
            if args.strategy == "hybrid":
                args.strategy = "recency"
                print("Note: Falling back to recency (vector store not available)")

        access_index = AccessIndex(repo.mem_dir)
        engine = RecallEngine(
            repo=repo,
            vector_store=vector_store,
            access_index=access_index,
            use_cache=not args.no_cache,
        )

        try:
            results = engine.recall(
                context=args.context,
                limit=args.limit,
                strategy=args.strategy,
                exclude=args.exclude,
            )
        except Exception as e:
            if _is_vector_unavailable_error(e):
                if args.strategy in ("similarity", "hybrid"):
                    print(
                        "Error: Vector search unavailable. Try --strategy recency or importance.",
                        file=sys.stderr,
                    )
                    return 1
                engine = RecallEngine(
                    repo=repo,
                    vector_store=None,
                    access_index=access_index,
                    use_cache=not args.no_cache,
                )
                results = engine.recall(
                    context=args.context,
                    limit=args.limit,
                    strategy="recency",
                    exclude=args.exclude,
                )
            else:
                raise

        if args.format == "json":
            output = [r.to_dict() for r in results]
            print(json.dumps(output, indent=2))
        else:
            for r in results:
                print(f"\n--- {r.path} (score: {r.relevance_score:.4f}) ---")
                print(r.content[:500] + ("..." if len(r.content) > 500 else ""))
                if r.importance is not None:
                    print(f"(importance: {r.importance})")

        if vector_store and hasattr(vector_store, "close"):
            vector_store.close()
        return 0
