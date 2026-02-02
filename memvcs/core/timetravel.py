"""
Time-Travel Debugging - Navigate memory history with temporal expressions.

This module provides:
- Time expression parsing (relative dates, ranges)
- Temporal checkout (view memory at any point in time)
- Knowledge snapshots with export
- Timeline navigation
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union


@dataclass
class TimeExpression:
    """Parsed time expression."""

    expression: str
    resolved_time: datetime
    is_relative: bool
    is_range: bool
    range_end: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expression": self.expression,
            "resolved_time": self.resolved_time.isoformat(),
            "is_relative": self.is_relative,
            "is_range": self.is_range,
            "range_end": self.range_end.isoformat() if self.range_end else None,
        }


class TimeExpressionParser:
    """Parses natural language time expressions."""

    RELATIVE_PATTERNS = [
        (r"(\d+)\s*(?:minutes?|min)\s*ago", lambda m: timedelta(minutes=int(m.group(1)))),
        (r"(\d+)\s*(?:hours?|hr)\s*ago", lambda m: timedelta(hours=int(m.group(1)))),
        (r"(\d+)\s*(?:days?)\s*ago", lambda m: timedelta(days=int(m.group(1)))),
        (r"(\d+)\s*(?:weeks?)\s*ago", lambda m: timedelta(weeks=int(m.group(1)))),
        (r"(\d+)\s*(?:months?)\s*ago", lambda m: timedelta(days=int(m.group(1)) * 30)),
        (r"(\d+)\s*(?:years?)\s*ago", lambda m: timedelta(days=int(m.group(1)) * 365)),
        (r"yesterday", lambda m: timedelta(days=1)),
        (r"last\s*week", lambda m: timedelta(weeks=1)),
        (r"last\s*month", lambda m: timedelta(days=30)),
        (r"today", lambda m: timedelta(days=0)),
        (r"now", lambda m: timedelta(seconds=0)),
    ]

    RANGE_PATTERNS = [
        # "between X and Y"
        (r"between\s+(.+?)\s+and\s+(.+)", 2),
        # "from X to Y"
        (r"from\s+(.+?)\s+to\s+(.+)", 2),
        # "last N days/weeks"
        (r"last\s+(\d+)\s+days?", lambda n: (int(n), "days")),
        (r"last\s+(\d+)\s+weeks?", lambda n: (int(n), "weeks")),
    ]

    def parse(self, expression: str) -> TimeExpression:
        """Parse a time expression into a TimeExpression object."""
        now = datetime.now(timezone.utc)
        expr_lower = expression.lower().strip()

        # Check for relative patterns
        for pattern, delta_fn in self.RELATIVE_PATTERNS:
            match = re.match(pattern, expr_lower)
            if match:
                delta = delta_fn(match)
                return TimeExpression(
                    expression=expression,
                    resolved_time=now - delta,
                    is_relative=True,
                    is_range=False,
                )

        # Check for range patterns
        if match := re.match(r"last\s+(\d+)\s+(days?|weeks?|months?)", expr_lower):
            count = int(match.group(1))
            unit = match.group(2).rstrip("s")
            if unit == "day":
                delta = timedelta(days=count)
            elif unit == "week":
                delta = timedelta(weeks=count)
            else:
                delta = timedelta(days=count * 30)

            return TimeExpression(
                expression=expression,
                resolved_time=now - delta,
                is_relative=True,
                is_range=True,
                range_end=now,
            )

        # Try ISO format
        for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
            try:
                dt = datetime.strptime(expr_lower, fmt).replace(tzinfo=timezone.utc)
                return TimeExpression(
                    expression=expression,
                    resolved_time=dt,
                    is_relative=False,
                    is_range=False,
                )
            except ValueError:
                continue

        # Default to now if unparseable
        return TimeExpression(
            expression=expression,
            resolved_time=now,
            is_relative=False,
            is_range=False,
        )

    def parse_range(self, start_expr: str, end_expr: str) -> Tuple[datetime, datetime]:
        """Parse a time range."""
        start = self.parse(start_expr).resolved_time
        end = self.parse(end_expr).resolved_time
        if start > end:
            start, end = end, start
        return start, end


@dataclass
class TemporalSnapshot:
    """A snapshot of memory state at a point in time."""

    timestamp: str
    commit_hash: str
    files: Dict[str, str]  # path -> content
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "commit_hash": self.commit_hash,
            "file_count": len(self.files),
            "files": list(self.files.keys()),
            "metadata": self.metadata,
        }


class TemporalNavigator:
    """Navigate memory history with time-based queries."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.parser = TimeExpressionParser()

    def find_commit_at(self, time_expr: str) -> Optional[Dict[str, Any]]:
        """Find the commit closest to a given time expression."""
        from memvcs.core.repository import Repository

        parsed = self.parser.parse(time_expr)
        target_time = parsed.resolved_time

        try:
            repo = Repository(self.repo_root)
            commits = repo.get_log(max_count=500)

            best_commit = None
            best_delta = None

            for commit in commits:
                ts = commit.get("timestamp", "")
                if ts:
                    try:
                        commit_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        delta = abs((commit_time - target_time).total_seconds())

                        # Only consider commits before or at the target time
                        if commit_time <= target_time:
                            if best_delta is None or delta < best_delta:
                                best_delta = delta
                                best_commit = commit
                    except Exception:
                        pass

            return best_commit
        except Exception:
            return None

    def find_commits_in_range(self, start_expr: str, end_expr: str) -> List[Dict[str, Any]]:
        """Find all commits within a time range."""
        from memvcs.core.repository import Repository

        start_time, end_time = self.parser.parse_range(start_expr, end_expr)

        try:
            repo = Repository(self.repo_root)
            commits = repo.get_log(max_count=500)

            matching = []
            for commit in commits:
                ts = commit.get("timestamp", "")
                if ts:
                    try:
                        commit_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if start_time <= commit_time <= end_time:
                            matching.append(commit)
                    except Exception:
                        pass

            return matching
        except Exception:
            return []

    def get_file_at_time(self, file_path: str, time_expr: str) -> Optional[str]:
        """Get file content at a specific point in time."""
        commit = self.find_commit_at(time_expr)
        if not commit:
            return None

        from memvcs.core.repository import Repository

        try:
            repo = Repository(self.repo_root)
            # Get file content from that commit
            # This is a simplified version - full implementation would
            # use object store to reconstruct file from tree
            return repo.get_file_content(file_path, commit["short_hash"])
        except Exception:
            return None

    def create_snapshot(self, time_expr: str) -> Optional[TemporalSnapshot]:
        """Create a snapshot of memory at a given time."""
        commit = self.find_commit_at(time_expr)
        if not commit:
            return None

        from memvcs.core.repository import Repository

        try:
            repo = Repository(self.repo_root)
            files = {}

            # Get all files from this commit
            for filepath in repo.current_dir.rglob("*"):
                if filepath.is_file():
                    try:
                        rel_path = str(filepath.relative_to(repo.current_dir))
                        content = repo.get_file_content(rel_path, commit["short_hash"])
                        if content:
                            files[rel_path] = content
                    except Exception:
                        pass

            return TemporalSnapshot(
                timestamp=commit.get("timestamp", ""),
                commit_hash=commit.get("short_hash", ""),
                files=files,
                metadata={
                    "message": commit.get("message", ""),
                    "author": commit.get("author", ""),
                },
            )
        except Exception:
            return None


class TimelineVisualizer:
    """Generates timeline data for visualization."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def get_activity_timeline(
        self, days: int = 30, granularity: str = "day"
    ) -> List[Dict[str, Any]]:
        """Get activity timeline data."""
        from memvcs.core.repository import Repository

        try:
            repo = Repository(self.repo_root)
            commits = repo.get_log(max_count=1000)

            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(days=days)

            # Group by granularity
            groups: Dict[str, List[Dict[str, Any]]] = {}
            for commit in commits:
                ts = commit.get("timestamp", "")
                if ts:
                    try:
                        commit_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if commit_time >= cutoff:
                            if granularity == "hour":
                                key = commit_time.strftime("%Y-%m-%d %H:00")
                            elif granularity == "day":
                                key = commit_time.strftime("%Y-%m-%d")
                            else:
                                key = commit_time.strftime("%Y-W%W")

                            if key not in groups:
                                groups[key] = []
                            groups[key].append(commit)
                    except Exception:
                        pass

            # Convert to list
            timeline = []
            for key in sorted(groups.keys()):
                commits_in_group = groups[key]
                timeline.append(
                    {
                        "period": key,
                        "count": len(commits_in_group),
                        "commits": [c["short_hash"] for c in commits_in_group[:5]],
                    }
                )

            return timeline
        except Exception:
            return []

    def get_file_activity_timeline(self, file_path: str, days: int = 90) -> List[Dict[str, Any]]:
        """Get activity timeline for a specific file."""
        from memvcs.core.repository import Repository

        try:
            repo = Repository(self.repo_root)
            commits = repo.get_log(max_count=500)

            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(days=days)

            # Filter to commits affecting this file
            # This is simplified - full implementation would check tree diffs
            timeline = []
            for commit in commits:
                ts = commit.get("timestamp", "")
                if ts:
                    try:
                        commit_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if commit_time >= cutoff:
                            timeline.append(
                                {
                                    "timestamp": ts,
                                    "commit": commit["short_hash"],
                                    "message": commit.get("message", ""),
                                }
                            )
                    except Exception:
                        pass

            return timeline[:50]  # Limit results
        except Exception:
            return []


class SnapshotExporter:
    """Exports temporal snapshots in various formats."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def export_json(self, snapshot: TemporalSnapshot) -> str:
        """Export snapshot as JSON."""
        data = {
            "timestamp": snapshot.timestamp,
            "commit_hash": snapshot.commit_hash,
            "files": snapshot.files,
            "metadata": snapshot.metadata,
        }
        return json.dumps(data, indent=2)

    def export_markdown(self, snapshot: TemporalSnapshot) -> str:
        """Export snapshot as Markdown."""
        lines = [
            f"# Memory Snapshot",
            f"",
            f"**Time:** {snapshot.timestamp}",
            f"**Commit:** {snapshot.commit_hash}",
            f"",
            f"## Files ({len(snapshot.files)})",
            "",
        ]

        for path, content in sorted(snapshot.files.items()):
            lines.append(f"### {path}")
            lines.append("```")
            lines.append(content[:500] + ("..." if len(content) > 500 else ""))
            lines.append("```")
            lines.append("")

        return "\n".join(lines)

    def export_archive(self, snapshot: TemporalSnapshot, output_dir: Path) -> Path:
        """Export snapshot as a file archive."""
        output_dir = Path(output_dir)
        archive_dir = output_dir / f"snapshot_{snapshot.commit_hash}"
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Write files
        for path, content in snapshot.files.items():
            file_path = archive_dir / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

        # Write metadata
        meta_file = archive_dir / "_snapshot_meta.json"
        meta_file.write_text(json.dumps(snapshot.metadata, indent=2))

        return archive_dir


# --- Dashboard Helper ---


def get_timetravel_dashboard(repo_root: Path) -> Dict[str, Any]:
    """Get data for time-travel dashboard."""
    navigator = TemporalNavigator(repo_root)
    visualizer = TimelineVisualizer(repo_root)

    timeline = visualizer.get_activity_timeline(days=30)

    return {
        "timeline": timeline,
        "timeline_days": 30,
        "total_commits": sum(t["count"] for t in timeline),
    }
