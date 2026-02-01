"""
Pack engine - context window budget manager for agmem.

Fills token budget with most relevant memories, optionally with summarization cascade.
"""

from typing import List, Optional, Any
from dataclasses import dataclass

from .base import RecallResult
from .recaller import RecallEngine


@dataclass
class PackResult:
    """Result of packing memories into budget."""

    content: str
    total_tokens: int
    budget: int
    items_used: int
    items_total: int


class PackEngine:
    """Packs recalled memories into a token budget."""

    def __init__(
        self,
        recall_engine: RecallEngine,
        model: str = "gpt-4o-mini",
        summarization_cascade: bool = False,
    ):
        self.recall_engine = recall_engine
        self.model = model
        self.summarization_cascade = summarization_cascade

    def _count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken."""
        try:
            import tiktoken

            enc = tiktoken.encoding_for_model(self.model)
            return len(enc.encode(text))
        except ImportError:
            # Fallback: ~4 chars per token
            return len(text) // 4
        except Exception:
            return len(text) // 4

    def pack(
        self,
        context: str,
        budget: int = 4000,
        strategy: str = "relevance",
        exclude: Optional[List[str]] = None,
    ) -> PackResult:
        """
        Pack memories into token budget.

        Args:
            context: Current task description for recall
            budget: Max tokens to use
            strategy: recall strategy (relevance=hybrid, recency, importance)
            exclude: Path patterns to exclude

        Returns:
            PackResult with packed content and metadata
        """
        exclude = exclude or []
        recall_strategy = "hybrid" if strategy == "relevance" else strategy
        if recall_strategy not in ("hybrid", "recency", "importance", "similarity"):
            recall_strategy = "hybrid"

        results = self.recall_engine.recall(
            context=context,
            limit=50,  # Get more candidates
            strategy=recall_strategy,
            exclude=exclude,
        )

        # Sort by relevance (already sorted by recall)
        # Add tokens, fill greedily
        total_tokens = 0
        packed_items: List[RecallResult] = []
        separator = "\n\n---\n\n"
        header = f"# Context for: {context}\n\n" if context else ""
        header_tokens = self._count_tokens(header)
        budget -= header_tokens

        for r in results:
            item_text = f"## {r.path}\n{r.content}"
            item_tokens = self._count_tokens(item_text)
            if total_tokens + item_tokens <= budget:
                packed_items.append(r)
                total_tokens += item_tokens
            else:
                # Try truncated
                if total_tokens < budget and item_tokens > 0:
                    ratio = (budget - total_tokens) / item_tokens
                    if ratio > 0.2:  # At least 20% of item
                        trunc_len = int(len(item_text) * ratio)
                        truncated = item_text[:trunc_len] + "\n..."
                        pack_tokens = self._count_tokens(truncated)
                        if total_tokens + pack_tokens <= budget:
                            r_trunc = RecallResult(
                                path=r.path,
                                content=r.content[: int(len(r.content) * ratio)] + "...",
                                relevance_score=r.relevance_score,
                                source=r.source,
                                importance=r.importance,
                            )
                            packed_items.append(r_trunc)
                            total_tokens += pack_tokens
                break

        content_parts = [r.content for r in packed_items]
        body = separator.join(content_parts)
        full_content = header + body
        total_tokens = header_tokens + self._count_tokens(body)

        return PackResult(
            content=full_content,
            total_tokens=total_tokens,
            budget=budget + header_tokens,
            items_used=len(packed_items),
            items_total=len(results),
        )
