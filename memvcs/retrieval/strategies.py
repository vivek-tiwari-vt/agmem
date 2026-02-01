"""
Recall strategies: recency, importance, similarity, hybrid.
"""

import fnmatch
from datetime import datetime
from pathlib import Path
from typing import List, Any, Optional

from .base import RetrievalStrategy, RecallResult
from ..core.constants import MEMORY_TYPES


def _matches_exclude(path: str, exclude: List[str]) -> bool:
    """Return True if path matches any exclude pattern."""
    if not exclude:
        return False
    for pattern in exclude:
        if fnmatch.fnmatch(path, pattern):
            return True
        if fnmatch.fnmatch(path, f"*/{pattern}"):
            return True
    return False


class RecencyStrategy(RetrievalStrategy):
    """Sort by commit timestamp / last_updated (newest first)."""

    def __init__(self, repo: Any):
        self.repo = repo

    def recall(
        self,
        context: str,
        limit: int,
        exclude: List[str],
        **kwargs: Any,
    ) -> List[RecallResult]:
        """Recall by recency - scan current/ and sort by mtime or frontmatter."""
        results = []
        current_dir = self.repo.current_dir
        if not current_dir.exists():
            return []

        for subdir in MEMORY_TYPES:
            dir_path = current_dir / subdir
            if not dir_path.exists():
                continue
            for f in dir_path.rglob("*"):
                if not f.is_file() or f.suffix.lower() not in (".md", ".txt"):
                    continue
                try:
                    rel_path = str(f.relative_to(current_dir))
                except ValueError:
                    continue
                if _matches_exclude(rel_path, exclude):
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                # Use mtime as recency proxy
                mtime = f.stat().st_mtime
                ts = datetime.fromtimestamp(mtime).isoformat() + "Z"

                results.append(
                    RecallResult(
                        path=rel_path,
                        content=content[:2000] + ("..." if len(content) > 2000 else ""),
                        relevance_score=1.0 / (1.0 + mtime),  # newer = higher
                        source={"indexed_at": ts, "commit_hash": None, "author": None},
                        importance=None,
                    )
                )

        # Sort by mtime descending (newest first)
        results.sort(key=lambda r: r.source.get("indexed_at", ""), reverse=True)
        return results[:limit]


class ImportanceStrategy(RetrievalStrategy):
    """Sort by importance from commit metadata."""

    def __init__(self, repo: Any):
        self.repo = repo

    def recall(
        self,
        context: str,
        limit: int,
        exclude: List[str],
        **kwargs: Any,
    ) -> List[RecallResult]:
        """Recall by importance - use commit metadata and frontmatter."""
        from ..core.objects import Commit, Blob, Tree
        from ..core.schema import FrontmatterParser

        results = []
        head = self.repo.get_head_commit()
        if not head:
            return []

        tree = self.repo.get_commit_tree(head.store(self.repo.object_store))
        if not tree:
            return []

        commit_importance = head.metadata.get("importance", 0.5)

        def collect_files(entries: list, prefix: str = "") -> None:
            for entry in entries:
                # Support both hierarchical trees and flat trees (entry.path = parent dir)
                path = (
                    f"{prefix}/{entry.path}/{entry.name}".replace("//", "/").lstrip("/")
                    if prefix or entry.path
                    else entry.name
                )
                if entry.obj_type == "tree":
                    subtree = Tree.load(self.repo.object_store, entry.hash)
                    if subtree:
                        collect_files(subtree.entries, path)
                else:
                    if _matches_exclude(path, exclude):
                        continue
                    blob = Blob.load(self.repo.object_store, entry.hash)
                    if not blob:
                        continue
                    try:
                        content = blob.content.decode("utf-8", errors="replace")
                    except Exception:
                        continue
                    fm, body = FrontmatterParser.parse(content)
                    importance = None
                    if fm and fm.importance is not None:
                        importance = fm.importance
                    elif fm and fm.confidence_score is not None:
                        importance = fm.confidence_score
                    else:
                        importance = commit_importance

                    results.append(
                        RecallResult(
                            path=path,
                            content=content[:2000] + ("..." if len(content) > 2000 else ""),
                            relevance_score=float(importance) if importance else 0.5,
                            source={
                                "commit_hash": head.store(self.repo.object_store),
                                "author": head.author,
                                "indexed_at": head.timestamp,
                            },
                            importance=float(importance) if importance else None,
                        )
                    )

        collect_files(tree.entries)
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:limit]


class SimilarityStrategy(RetrievalStrategy):
    """Use vector store for embedding similarity."""

    def __init__(self, repo: Any, vector_store: Any):
        self.repo = repo
        self.vector_store = vector_store

    def recall(
        self,
        context: str,
        limit: int,
        exclude: List[str],
        **kwargs: Any,
    ) -> List[RecallResult]:
        """Recall by semantic similarity to context."""
        raw = self.vector_store.search_with_provenance(context, limit=limit * 2)
        results = []
        for item in raw:
            path = item.get("path", "")
            if _matches_exclude(path, exclude):
                continue
            results.append(
                RecallResult(
                    path=path,
                    content=item.get("content", ""),
                    relevance_score=item.get("similarity", 1.0 - item.get("distance", 0)),
                    source={
                        "commit_hash": item.get("commit_hash"),
                        "author": item.get("author"),
                        "indexed_at": item.get("indexed_at"),
                        "blob_hash": item.get("blob_hash"),
                    },
                    importance=None,
                )
            )
            if len(results) >= limit:
                break
        return results


class HybridStrategy(RetrievalStrategy):
    """Weighted combo of similarity, recency, importance."""

    def __init__(
        self,
        repo: Any,
        vector_store: Optional[Any] = None,
        weights: Optional[dict] = None,
    ):
        self.repo = repo
        self.vector_store = vector_store
        self.weights = weights or {
            "similarity": 0.4,
            "recency": 0.3,
            "importance": 0.3,
        }

    def recall(
        self,
        context: str,
        limit: int,
        exclude: List[str],
        **kwargs: Any,
    ) -> List[RecallResult]:
        """Combine strategies with configurable weights."""
        from ..core.schema import FrontmatterParser

        # Collect candidates from all sources
        path_to_result: dict = {}

        # Similarity (if vector store available)
        if self.vector_store:
            sim = SimilarityStrategy(self.repo, self.vector_store)
            for r in sim.recall(context, limit * 2, exclude):
                path_to_result[r.path] = {
                    "result": r,
                    "sim_score": r.relevance_score,
                    "rec_score": 0.5,
                    "imp_score": r.importance or 0.5,
                }

        # Recency and importance from current/
        current_dir = self.repo.current_dir
        if current_dir.exists():
            import time

            head = self.repo.get_head_commit()
            commit_imp = head.metadata.get("importance", 0.5) if head else 0.5

            for subdir in MEMORY_TYPES:
                dir_path = current_dir / subdir
                if not dir_path.exists():
                    continue
                for f in dir_path.rglob("*"):
                    if not f.is_file() or f.suffix.lower() not in (".md", ".txt"):
                        continue
                    try:
                        rel_path = str(f.relative_to(current_dir))
                    except ValueError:
                        continue
                    if _matches_exclude(rel_path, exclude):
                        continue
                    try:
                        content = f.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        continue

                    mtime = f.stat().st_mtime
                    rec_score = 1.0 - (time.time() - mtime) / (86400 * 30)  # normalize to ~30 days
                    rec_score = max(0, min(1, rec_score))

                    fm, _ = FrontmatterParser.parse(content)
                    imp_score = 0.5
                    if fm and fm.importance is not None:
                        imp_score = fm.importance
                    elif fm and fm.confidence_score is not None:
                        imp_score = fm.confidence_score
                    else:
                        imp_score = commit_imp

                    if rel_path in path_to_result:
                        path_to_result[rel_path]["rec_score"] = rec_score
                        path_to_result[rel_path]["imp_score"] = imp_score
                    else:
                        path_to_result[rel_path] = {
                            "result": RecallResult(
                                path=rel_path,
                                content=content[:2000] + ("..." if len(content) > 2000 else ""),
                                relevance_score=0,
                                source={
                                    "indexed_at": datetime.fromtimestamp(mtime).isoformat() + "Z"
                                },
                                importance=imp_score,
                            ),
                            "sim_score": 0.5,
                            "rec_score": rec_score,
                            "imp_score": imp_score,
                        }

        # Compute hybrid score
        w = self.weights
        scored = []
        for path, data in path_to_result.items():
            score = (
                w.get("similarity", 0.33) * data["sim_score"]
                + w.get("recency", 0.33) * data["rec_score"]
                + w.get("importance", 0.33) * data["imp_score"]
            )
            r = data["result"]
            r.relevance_score = score
            r.importance = data.get("imp_score")
            scored.append(r)

        scored.sort(key=lambda x: x.relevance_score, reverse=True)
        return scored[:limit]
