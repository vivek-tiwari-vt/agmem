"""
agmem pack - Context window budget manager.

Packs recalled memories into token budget for LLM injection.
"""

import argparse
import sys
from pathlib import Path

from ..commands.base import require_repo
from ..core.access_index import AccessIndex
from ..retrieval import RecallEngine
from ..retrieval.pack import PackEngine


class PackCommand:
    """Context window budget manager."""

    name = "pack"
    help = "Pack recalled memories into token budget for LLM context"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "--context",
            "-c",
            default="",
            help="Current task description for recall",
        )
        parser.add_argument(
            "--budget",
            "-b",
            type=int,
            default=4000,
            help="Max tokens (default: 4000)",
        )
        parser.add_argument(
            "--strategy",
            "-s",
            choices=["relevance", "recency", "importance", "balanced"],
            default="relevance",
            help="Packing strategy (default: relevance)",
        )
        parser.add_argument(
            "--exclude",
            "-e",
            action="append",
            default=[],
            help="Paths to exclude; repeatable",
        )
        parser.add_argument(
            "--model",
            "-m",
            default="gpt-4o-mini",
            help="Model for token counting (default: gpt-4o-mini)",
        )
        parser.add_argument(
            "--format",
            "-f",
            choices=["text", "json"],
            default="text",
            help="Output format (default: text)",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        vector_store = None
        try:
            from ..core.vector_store import VectorStore

            vs = VectorStore(repo.mem_dir)
            vs._get_connection()  # ensure sqlite-vec is usable; may raise
            vector_store = vs
        except Exception:
            pass

        access_index = AccessIndex(repo.mem_dir)
        recall_engine = RecallEngine(
            repo=repo,
            vector_store=vector_store,
            access_index=access_index,
            use_cache=True,
        )

        strategy = "hybrid" if args.strategy == "balanced" else args.strategy
        pack_engine = PackEngine(
            recall_engine=recall_engine,
            model=args.model,
            summarization_cascade=False,
        )

        result = pack_engine.pack(
            context=args.context,
            budget=args.budget,
            strategy=strategy,
            exclude=args.exclude,
        )

        if args.format == "json":
            import json

            print(
                json.dumps(
                    {
                        "content": result.content,
                        "total_tokens": result.total_tokens,
                        "budget": result.budget,
                        "items_used": result.items_used,
                        "items_total": result.items_total,
                    },
                    indent=2,
                )
            )
        else:
            print(result.content)
            print(
                f"\n# Pack stats: {result.total_tokens}/{result.budget} tokens, "
                f"{result.items_used}/{result.items_total} items",
                file=sys.stderr,
            )

        if vector_store and hasattr(vector_store, "close"):
            vector_store.close()
        return 0
