"""
Temporal index for agmem - maps timestamps to commits for time-travel queries.

Builds index from reflog and commit objects; binary search for nearest commit at or before T.
"""

import bisect
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

from .objects import Commit, ObjectStore


def _parse_iso_timestamp(s: str) -> Optional[datetime]:
    """Parse ISO 8601 timestamp string to datetime."""
    s = s.strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


class TemporalIndex:
    """Maps timestamps to commit hashes for temporal querying."""

    def __init__(self, mem_dir: Path, object_store: ObjectStore):
        self.mem_dir = Path(mem_dir)
        self.object_store = object_store
        self.refs = None  # Injected by caller

    def _build_commit_timeline(self) -> List[Tuple[datetime, str]]:
        """
        Build sorted list of (timestamp, commit_hash) from reflog and all commits.

        Walks HEAD reflog and follow parent chains to collect all commits with timestamps.
        """
        from .refs import RefsManager

        refs = RefsManager(self.mem_dir)
        seen = set()
        timeline: List[Tuple[datetime, str]] = []

        # Collect from reflog first (recent history)
        reflog = refs.get_reflog("HEAD", max_count=10000)
        for entry in reflog:
            h = entry.get("hash")
            ts_str = entry.get("timestamp", "")
            if h and ts_str and h not in seen:
                dt = _parse_iso_timestamp(ts_str)
                if dt:
                    seen.add(h)
                    timeline.append((dt, h))

        # Also walk from HEAD and all branches to get full history
        def walk_commits(commit_hash: str) -> None:
            current = commit_hash
            while current and current not in seen:
                commit = Commit.load(self.object_store, current)
                if not commit:
                    break
                seen.add(current)
                dt = _parse_iso_timestamp(commit.timestamp)
                if dt:
                    timeline.append((dt, current))
                if not commit.parents:
                    break
                current = commit.parents[0]

        head = refs.get_head()
        if head["type"] == "branch":
            h = refs.get_branch_commit(head["value"])
        else:
            h = head.get("value")
        if h:
            walk_commits(h)

        for branch in refs.list_branches():
            bh = refs.get_branch_commit(branch)
            if bh:
                walk_commits(bh)

        timeline.sort(key=lambda x: x[0])
        return timeline

    def resolve_at(self, timestamp_str: str) -> Optional[str]:
        """
        Resolve timestamp to nearest commit at or before that time.

        Args:
            timestamp_str: ISO 8601 date or datetime (e.g., "2025-12-01", "2025-12-01T14:00:00")

        Returns:
            Commit hash or None if no commit found
        """
        dt = _parse_iso_timestamp(timestamp_str)
        if not dt:
            return None

        timeline = self._build_commit_timeline()
        if not timeline:
            return None

        timestamps = [t[0] for t in timeline]
        idx = bisect.bisect_right(timestamps, dt)
        if idx == 0:
            return None  # All commits are after the requested time
        return timeline[idx - 1][1]
