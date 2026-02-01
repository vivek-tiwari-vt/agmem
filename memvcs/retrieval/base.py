"""
Base retrieval interfaces for agmem recall.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Any, Optional


@dataclass
class RecallResult:
    """Single recalled memory with metadata."""

    path: str
    content: str
    relevance_score: float
    source: dict  # commit_hash, author, indexed_at, etc.
    importance: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "path": self.path,
            "content": self.content,
            "relevance_score": self.relevance_score,
            "source": self.source,
            "importance": self.importance,
        }


class RetrievalStrategy(ABC):
    """Abstract base for recall strategies."""

    @abstractmethod
    def recall(
        self,
        context: str,
        limit: int,
        exclude: List[str],
        **kwargs: Any,
    ) -> List[RecallResult]:
        """
        Retrieve and rank memories for the given context.

        Args:
            context: Current task description
            limit: Max results to return
            exclude: Tag/branch patterns to exclude (e.g., "experiment/*")
            **kwargs: Strategy-specific options

        Returns:
            Ranked list of RecallResult
        """
        pass
