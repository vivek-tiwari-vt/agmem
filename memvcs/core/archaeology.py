"""
Memory Archaeology - Deep history exploration and analysis tools.

This module provides:
- Historical context reconstruction
- Memory evolution tracking
- Forgotten knowledge discovery
- Pattern analysis across time
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class MemoryEvolution:
    """Tracks how a memory file evolved over time."""

    path: str
    first_seen: str
    last_modified: str
    version_count: int
    commits: List[str]
    size_history: List[Tuple[str, int]]  # (timestamp, size)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "first_seen": self.first_seen,
            "last_modified": self.last_modified,
            "version_count": self.version_count,
            "commits": self.commits,
            "size_history": self.size_history,
        }


@dataclass
class ForgottenMemory:
    """A memory that hasn't been accessed recently."""

    path: str
    last_accessed: str
    days_since_access: int
    content_preview: str
    memory_type: str
    relevance_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "last_accessed": self.last_accessed,
            "days_since_access": self.days_since_access,
            "content_preview": self.content_preview,
            "memory_type": self.memory_type,
            "relevance_score": self.relevance_score,
        }


@dataclass
class TemporalPattern:
    """A pattern in memory activity over time."""

    pattern_type: str  # "burst", "periodic", "declining", "growing"
    description: str
    files_involved: List[str]
    time_range: Tuple[str, str]
    confidence: float


class HistoryExplorer:
    """Explores memory history across commits."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def get_file_history(self, relative_path: str, max_commits: int = 50) -> List[Dict[str, Any]]:
        """Get commit history for a specific file."""
        try:
            from memvcs.core.repository import Repository

            repo = Repository(self.repo_root)
            commits = repo.get_log(max_count=max_commits)

            file_commits = []
            for commit_info in commits:
                # Check if file was in this commit's tree
                # This is a simplified check - full implementation would walk the tree
                file_commits.append(
                    {
                        "commit": commit_info["short_hash"],
                        "message": commit_info["message"],
                        "timestamp": commit_info.get("timestamp", ""),
                        "author": commit_info.get("author", ""),
                    }
                )

            return file_commits[:max_commits]
        except Exception:
            return []

    def get_memory_evolution(self, relative_path: str) -> Optional[MemoryEvolution]:
        """Track how a memory file evolved."""
        try:
            from memvcs.core.repository import Repository

            repo = Repository(self.repo_root)
            commits = repo.get_log(max_count=100)

            if not commits:
                return None

            first_seen = commits[-1].get("timestamp", "")
            last_modified = commits[0].get("timestamp", "")
            commit_hashes = [c["short_hash"] for c in commits]

            return MemoryEvolution(
                path=relative_path,
                first_seen=first_seen,
                last_modified=last_modified,
                version_count=len(commits),
                commits=commit_hashes,
                size_history=[],  # Would require content at each commit
            )
        except Exception:
            return None

    def compare_versions(self, path: str, commit1: str, commit2: str) -> Dict[str, Any]:
        """Compare two versions of a file."""
        try:
            from memvcs.core.repository import Repository
            from memvcs.core.diff import DiffEngine

            repo = Repository(self.repo_root)
            engine = DiffEngine(repo.object_store)

            diff = engine.diff_commits(commit1, commit2)

            return {
                "path": path,
                "from_commit": commit1,
                "to_commit": commit2,
                "has_changes": len(diff.files) > 0,
                "files_changed": len(diff.files),
            }
        except Exception as e:
            return {"error": str(e)}


class ForgottenKnowledgeFinder:
    """Discovers forgotten or under-utilized memories."""

    def __init__(self, repo_root: Path, access_log_path: Optional[Path] = None):
        self.repo_root = Path(repo_root)
        self.mem_dir = self.repo_root / ".mem"
        self.access_log = access_log_path or (self.mem_dir / "access.log")

    def _load_access_times(self) -> Dict[str, str]:
        """Load last access times from log."""
        access_times = {}
        if self.access_log.exists():
            try:
                for line in self.access_log.read_text().strip().split("\n"):
                    if line:
                        parts = line.split("|")
                        if len(parts) >= 2:
                            access_times[parts[1]] = parts[0]
            except Exception:
                pass
        return access_times

    def find_forgotten(self, days_threshold: int = 30, limit: int = 20) -> List[ForgottenMemory]:
        """Find memories not accessed in the given time period."""
        from memvcs.core.repository import Repository

        try:
            repo = Repository(self.repo_root)
            current_dir = repo.current_dir

            access_times = self._load_access_times()
            now = datetime.now(timezone.utc)
            threshold = now - timedelta(days=days_threshold)

            forgotten = []
            for filepath in current_dir.rglob("*"):
                if not filepath.is_file():
                    continue

                rel_path = str(filepath.relative_to(current_dir))

                # Determine last access
                if rel_path in access_times:
                    last_access = access_times[rel_path]
                else:
                    # Use modification time as fallback
                    mtime = filepath.stat().st_mtime
                    last_access = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

                try:
                    last_dt = datetime.fromisoformat(last_access.replace("Z", "+00:00"))
                    if last_dt < threshold:
                        days_ago = (now - last_dt).days
                        content = filepath.read_text(encoding="utf-8", errors="replace")[:200]
                        memory_type = self._infer_memory_type(filepath)

                        forgotten.append(
                            ForgottenMemory(
                                path=rel_path,
                                last_accessed=last_access,
                                days_since_access=days_ago,
                                content_preview=content,
                                memory_type=memory_type,
                            )
                        )
                except Exception:
                    pass

            # Sort by days since access (oldest first)
            forgotten.sort(key=lambda x: x.days_since_access, reverse=True)
            return forgotten[:limit]

        except Exception:
            return []

    def _infer_memory_type(self, filepath: Path) -> str:
        """Infer memory type from path."""
        parts = filepath.parts
        for mt in ["episodic", "semantic", "procedural"]:
            if mt in parts:
                return mt
        return "unknown"

    def rediscover_relevant(self, query: str, days_threshold: int = 30) -> List[ForgottenMemory]:
        """Find forgotten memories relevant to a query."""
        forgotten = self.find_forgotten(days_threshold=days_threshold, limit=100)

        # Simple relevance scoring based on query terms
        query_terms = set(query.lower().split())

        for memory in forgotten:
            content_lower = memory.content_preview.lower()
            matches = sum(1 for term in query_terms if term in content_lower)
            memory.relevance_score = matches / max(1, len(query_terms))

        # Sort by relevance
        forgotten.sort(key=lambda x: x.relevance_score, reverse=True)
        return [m for m in forgotten if m.relevance_score > 0][:20]


class PatternAnalyzer:
    """Analyzes temporal patterns in memory activity."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def analyze_activity_patterns(self, days: int = 90) -> List[TemporalPattern]:
        """Analyze patterns in memory activity."""
        from memvcs.core.repository import Repository

        patterns = []

        try:
            repo = Repository(self.repo_root)
            commits = repo.get_log(max_count=500)

            if len(commits) < 5:
                return []

            # Group commits by day
            by_day: Dict[str, int] = {}
            for commit in commits:
                ts = commit.get("timestamp", "")[:10]
                if ts:
                    by_day[ts] = by_day.get(ts, 0) + 1

            # Detect patterns
            sorted_days = sorted(by_day.keys())

            if sorted_days:
                # Check for bursts (days with >3x average)
                avg_commits = sum(by_day.values()) / len(by_day)
                burst_days = [d for d, c in by_day.items() if c > avg_commits * 3]
                if burst_days:
                    patterns.append(
                        TemporalPattern(
                            pattern_type="burst",
                            description=f"High activity bursts on {len(burst_days)} days",
                            files_involved=[],
                            time_range=(burst_days[0], burst_days[-1]),
                            confidence=0.8,
                        )
                    )

                # Check for declining activity
                recent_30 = [
                    c for d, c in by_day.items() if d >= sorted_days[-30] if len(sorted_days) >= 30
                ]
                older_30 = [
                    c for d, c in by_day.items() if d < sorted_days[-30] if len(sorted_days) >= 60
                ]
                if recent_30 and older_30:
                    recent_avg = sum(recent_30) / len(recent_30)
                    older_avg = sum(older_30) / len(older_30)
                    if recent_avg < older_avg * 0.5:
                        patterns.append(
                            TemporalPattern(
                                pattern_type="declining",
                                description="Activity has declined significantly",
                                files_involved=[],
                                time_range=(sorted_days[0], sorted_days[-1]),
                                confidence=0.7,
                            )
                        )

        except Exception:
            pass

        return patterns

    def get_memory_hotspots(self, days: int = 30) -> List[Dict[str, Any]]:
        """Find most frequently modified memories."""
        from memvcs.core.repository import Repository

        try:
            repo = Repository(self.repo_root)
            commits = repo.get_log(max_count=100)

            # This is a simplified version - full implementation would
            # track which files changed in each commit
            file_activity: Dict[str, int] = {}

            # Count commits as proxy for activity
            return [
                {"path": path, "activity_count": count}
                for path, count in sorted(file_activity.items(), key=lambda x: -x[1])[:10]
            ]
        except Exception:
            return []


class ContextReconstructor:
    """Reconstructs historical context around memories."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def reconstruct_context(
        self, path: str, target_date: str, window_days: int = 7
    ) -> Dict[str, Any]:
        """Reconstruct what was happening around a memory at a point in time."""
        from memvcs.core.repository import Repository

        try:
            repo = Repository(self.repo_root)
            commits = repo.get_log(max_count=500)

            # Find commits around target date
            target_dt = datetime.fromisoformat(target_date.replace("Z", "+00:00"))
            window_start = target_dt - timedelta(days=window_days)
            window_end = target_dt + timedelta(days=window_days)

            nearby_commits = []
            for commit in commits:
                ts = commit.get("timestamp", "")
                if ts:
                    try:
                        commit_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if window_start <= commit_dt <= window_end:
                            nearby_commits.append(commit)
                    except Exception:
                        pass

            return {
                "target_path": path,
                "target_date": target_date,
                "window_days": window_days,
                "commits_in_window": len(nearby_commits),
                "commits": nearby_commits[:20],
                "summary": f"Found {len(nearby_commits)} commits within {window_days} days of {target_date[:10]}",
            }
        except Exception as e:
            return {"error": str(e)}


# --- Dashboard Helper ---


def get_archaeology_dashboard(repo_root: Path) -> Dict[str, Any]:
    """Get data for memory archaeology dashboard."""
    pattern_analyzer = PatternAnalyzer(repo_root)
    forgotten_finder = ForgottenKnowledgeFinder(repo_root)

    forgotten = forgotten_finder.find_forgotten(days_threshold=30, limit=10)
    patterns = pattern_analyzer.analyze_activity_patterns(days=90)

    return {
        "forgotten_memories": [f.to_dict() for f in forgotten],
        "forgotten_count": len(forgotten),
        "activity_patterns": [
            {
                "type": p.pattern_type,
                "description": p.description,
                "confidence": p.confidence,
            }
            for p in patterns
        ],
    }
