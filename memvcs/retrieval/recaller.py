"""
Recall engine - orchestrates strategies and access tracking.
"""

from typing import List, Optional, Any

from .base import RetrievalStrategy, RecallResult
from .strategies import RecencyStrategy, ImportanceStrategy, SimilarityStrategy, HybridStrategy


class RecallEngine:
    """Orchestrates recall with pluggable strategies and access tracking."""

    STRATEGIES = ["recency", "importance", "similarity", "hybrid"]

    def __init__(
        self,
        repo: Any,
        vector_store: Optional[Any] = None,
        access_index: Optional[Any] = None,
        use_cache: bool = True,
    ):
        self.repo = repo
        self.vector_store = vector_store
        self.access_index = access_index
        self.use_cache = use_cache

    def _get_strategy(self, strategy_name: str) -> RetrievalStrategy:
        """Get strategy instance by name."""
        name = strategy_name.lower()
        if name == "recency":
            return RecencyStrategy(self.repo)
        if name == "importance":
            return ImportanceStrategy(self.repo)
        if name == "similarity":
            if not self.vector_store:
                raise ImportError(
                    "Similarity strategy requires agmem[vector]. Install with: pip install agmem[vector]"
                )
            return SimilarityStrategy(self.repo, self.vector_store)
        if name == "hybrid":
            return HybridStrategy(self.repo, self.vector_store)
        raise ValueError(f"Unknown strategy: {strategy_name}. Choose from {self.STRATEGIES}")

    def recall(
        self,
        context: str,
        limit: int = 10,
        strategy: str = "hybrid",
        exclude: Optional[List[str]] = None,
    ) -> List[RecallResult]:
        """
        Recall memories for the given context.

        Args:
            context: Current task description
            limit: Max results
            strategy: recency, importance, similarity, or hybrid
            exclude: Tag/path patterns to exclude

        Returns:
            Ranked list of RecallResult
        """
        exclude_list = [e.strip() for e in (exclude or []) if e.strip()]

        cached = self._get_cached_results(context, strategy, limit, exclude_list)
        if cached is not None:
            return cached

        effective_strategy = (
            "recency" if (strategy == "hybrid" and not self.vector_store) else strategy
        )
        strat = self._get_strategy(effective_strategy)
        results = strat.recall(context=context, limit=limit, exclude=exclude_list)

        self._record_access_and_cache(context, effective_strategy, limit, exclude_list, results)
        return results

    def _get_cached_results(
        self, context: str, strategy: str, limit: int, exclude: List[str]
    ) -> Optional[List[RecallResult]]:
        if not (self.use_cache and self.access_index and context):
            return None
        cached = self.access_index.get_cached_recall(context, strategy, limit, exclude)
        if not cached or not cached.get("results"):
            return None
        return [RecallResult(**r) if isinstance(r, dict) else r for r in cached["results"]]

    def _record_access_and_cache(
        self,
        context: str,
        strategy: str,
        limit: int,
        exclude: List[str],
        results: List[RecallResult],
    ) -> None:
        if self.access_index:
            head = self.repo.get_head_commit()
            commit_hash = head.store(self.repo.object_store) if head else ""
            for r in results:
                self.access_index.record_access(r.path, commit_hash)
        if self.use_cache and self.access_index and context and results:
            self.access_index.set_cached_recall(
                context, strategy, limit, exclude, [r.to_dict() for r in results]
            )
