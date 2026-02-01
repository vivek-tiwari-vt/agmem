"""
Access index for agmem - tracks recall access patterns for importance weighting and decay.

Stores access log and recall cache in .mem/index.json.
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Maximum entries in access log before compaction
ACCESS_LOG_MAX = 10_000


class AccessIndex:
    """Tracks access patterns for recall, importance, and decay."""

    def __init__(self, mem_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.index_path = self.mem_dir / "index.json"
        self._data: Optional[Dict[str, Any]] = None

    def _load(self) -> Dict[str, Any]:
        """Load index from disk."""
        if self._data is not None:
            return self._data
        if self.index_path.exists():
            try:
                self._data = json.loads(self.index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = self._default_structure()
        else:
            self._data = self._default_structure()
        return self._data

    def _default_structure(self) -> Dict[str, Any]:
        """Return default index structure."""
        return {
            "version": 1,
            "access_log": [],
            "recall_cache": {},
        }

    def _save(self, data: Optional[Dict[str, Any]] = None) -> None:
        """Save index to disk."""
        data = data or self._data
        if data is None:
            return
        self.mem_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._data = data

    def record_access(self, path: str, commit: str, timestamp: Optional[str] = None) -> None:
        """
        Record that a memory file was accessed (e.g., during recall).

        Args:
            path: File path relative to current/
            commit: Commit hash at time of access
            timestamp: ISO 8601 timestamp (default: now)
        """
        data = self._load()
        ts = timestamp or datetime.utcnow().isoformat() + "Z"
        data["access_log"].append({"path": path, "commit": commit, "timestamp": ts})
        self._trim_access_log_if_needed(data)
        self._save()

    def _trim_access_log_if_needed(self, data: Dict[str, Any]) -> None:
        if len(data.get("access_log", [])) > ACCESS_LOG_MAX:
            data["access_log"] = data["access_log"][-ACCESS_LOG_MAX:]

    def get_access_count(self, path: Optional[str] = None, commit: Optional[str] = None) -> int:
        """
        Get access count for a path and/or commit.

        Args:
            path: Filter by path (None = any)
            commit: Filter by commit (None = any)

        Returns:
            Number of matching access entries
        """
        data = self._load()
        entries = data.get("access_log", [])
        count = 0
        for entry in entries:
            if path is not None and entry.get("path") != path:
                continue
            if commit is not None and entry.get("commit") != commit:
                continue
            count += 1
        return count

    def get_recent_accesses(
        self,
        limit: int = 100,
        path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get most recent access entries.

        Args:
            limit: Max entries to return
            path: Filter by path (None = any)

        Returns:
            List of access entries (newest first)
        """
        data = self._load()
        entries = data.get("access_log", [])
        if path is not None:
            entries = [e for e in entries if e.get("path") == path]
        return list(reversed(entries[-limit:]))

    def get_access_counts_by_path(self) -> Dict[str, int]:
        """Aggregate access counts per path (for importance weighting)."""
        data = self._load()
        counts: Dict[str, int] = {}
        for entry in data.get("access_log", []):
            p = entry.get("path", "")
            counts[p] = counts.get(p, 0) + 1
        return counts

    def get_cache_key(self, context: str, strategy: str, limit: int, exclude: List[str]) -> str:
        """Compute cache key for recall results."""
        payload = f"{context}|{strategy}|{limit}|{','.join(sorted(exclude))}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def get_cached_recall(
        self,
        context: str,
        strategy: str,
        limit: int,
        exclude: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Get cached recall results if available."""
        key = self.get_cache_key(context, strategy, limit, exclude)
        data = self._load()
        cache = data.get("recall_cache", {})
        return cache.get(key)

    def set_cached_recall(
        self,
        context: str,
        strategy: str,
        limit: int,
        exclude: List[str],
        results: List[Dict[str, Any]],
    ) -> None:
        """Cache recall results."""
        key = self.get_cache_key(context, strategy, limit, exclude)
        data = self._load()
        if "recall_cache" not in data:
            data["recall_cache"] = {}
        data["recall_cache"][key] = {
            "results": results,
            "cached_at": datetime.utcnow().isoformat() + "Z",
        }
        # Limit cache size
        cache = data["recall_cache"]
        if len(cache) > 100:
            oldest = sorted(cache.items(), key=lambda x: x[1].get("cached_at", ""))[:50]
            for k, _ in oldest:
                del cache[k]
        self._save()
