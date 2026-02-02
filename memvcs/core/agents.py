"""
Memory Agents - Automated memory management tasks.

This module provides:
- Automated memory consolidation
- Cleanup and archival agents
- Pattern detection and alerts
- Proactive memory maintenance
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class AgentTask:
    """A task for a memory agent to execute."""

    task_id: str
    task_type: str  # "consolidate", "cleanup", "archive", "alert"
    target: str  # Path or pattern
    priority: int = 1  # 1=low, 5=high
    scheduled_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "target": self.target,
            "priority": self.priority,
            "scheduled_at": self.scheduled_at,
            "completed_at": self.completed_at,
            "result": self.result,
        }


@dataclass
class AgentRule:
    """A rule that triggers agent actions."""

    rule_id: str
    name: str
    condition: str  # Type of condition
    threshold: Any  # Threshold value
    action: str  # Action to take
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "condition": self.condition,
            "threshold": self.threshold,
            "action": self.action,
            "enabled": self.enabled,
        }


class ConsolidationAgent:
    """Agent that consolidates fragmented memories."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def find_consolidation_candidates(
        self, min_similarity: float = 0.7, max_age_days: int = 30
    ) -> List[Dict[str, Any]]:
        """Find memories that could be consolidated."""
        from memvcs.core.repository import Repository

        candidates = []
        try:
            repo = Repository(self.repo_root)
            current_dir = repo.current_dir

            # Group files by topic/similarity
            files_by_prefix: Dict[str, List[Path]] = {}
            for filepath in current_dir.rglob("*.md"):
                if filepath.is_file():
                    # Group by directory + first word of filename
                    prefix = filepath.parent.name + "/" + filepath.stem.split("-")[0]
                    if prefix not in files_by_prefix:
                        files_by_prefix[prefix] = []
                    files_by_prefix[prefix].append(filepath)

            # Find groups with multiple files
            for prefix, files in files_by_prefix.items():
                if len(files) >= 3:
                    candidates.append(
                        {
                            "prefix": prefix,
                            "file_count": len(files),
                            "files": [str(f.relative_to(current_dir)) for f in files[:5]],
                            "suggestion": f"Consider consolidating {len(files)} related files",
                        }
                    )
        except Exception:
            pass

        return candidates[:20]

    def consolidate(self, file_paths: List[str], output_path: str) -> Dict[str, Any]:
        """Consolidate multiple memories into one."""
        from memvcs.core.repository import Repository

        try:
            repo = Repository(self.repo_root)
            current_dir = repo.current_dir

            combined_content = []
            combined_content.append(f"# Consolidated Memory\n")
            combined_content.append(f"Created: {datetime.now(timezone.utc).isoformat()}\n")
            combined_content.append(f"Sources: {len(file_paths)} files\n\n")

            for path in file_paths:
                full_path = current_dir / path
                if full_path.exists():
                    content = full_path.read_text()
                    combined_content.append(f"## From: {path}\n\n")
                    combined_content.append(content)
                    combined_content.append("\n\n---\n\n")

            # Write consolidated file
            output_full = current_dir / output_path
            output_full.parent.mkdir(parents=True, exist_ok=True)
            output_full.write_text("\n".join(combined_content))

            return {
                "success": True,
                "output_path": output_path,
                "source_count": len(file_paths),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class CleanupAgent:
    """Agent that identifies and cleans up old/unused memories."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def find_cleanup_candidates(
        self, max_age_days: int = 90, min_size_bytes: int = 0
    ) -> List[Dict[str, Any]]:
        """Find memories that are candidates for cleanup."""
        from memvcs.core.repository import Repository

        candidates = []
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max_age_days)

        try:
            repo = Repository(self.repo_root)
            current_dir = repo.current_dir

            for filepath in current_dir.rglob("*"):
                if not filepath.is_file():
                    continue

                stat = filepath.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

                if mtime < cutoff:
                    rel_path = str(filepath.relative_to(current_dir))
                    candidates.append(
                        {
                            "path": rel_path,
                            "size_bytes": stat.st_size,
                            "last_modified": mtime.isoformat(),
                            "age_days": (now - mtime).days,
                        }
                    )
        except Exception:
            pass

        # Sort by age
        candidates.sort(key=lambda x: x["age_days"], reverse=True)
        return candidates[:50]

    def find_duplicates(self) -> List[Dict[str, Any]]:
        """Find duplicate memories."""
        from memvcs.core.repository import Repository

        try:
            repo = Repository(self.repo_root)
            current_dir = repo.current_dir

            hash_to_files: Dict[str, List[str]] = {}

            for filepath in current_dir.rglob("*"):
                if filepath.is_file():
                    try:
                        content_hash = hashlib.sha256(filepath.read_bytes()).hexdigest()[:16]

                        rel_path = str(filepath.relative_to(current_dir))
                        if content_hash not in hash_to_files:
                            hash_to_files[content_hash] = []
                        hash_to_files[content_hash].append(rel_path)
                    except Exception:
                        pass

            duplicates = []
            for hash_val, files in hash_to_files.items():
                if len(files) > 1:
                    duplicates.append(
                        {
                            "hash": hash_val,
                            "files": files,
                            "count": len(files),
                        }
                    )

            return duplicates
        except Exception:
            return []

    def archive_old_memories(
        self, paths: List[str], archive_dir: str = "archive"
    ) -> Dict[str, Any]:
        """Move old memories to archive."""
        from memvcs.core.repository import Repository

        try:
            repo = Repository(self.repo_root)
            current_dir = repo.current_dir
            archive_path = current_dir / archive_dir

            archived = []
            for path in paths:
                source = current_dir / path
                if source.exists():
                    dest = archive_path / path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    source.rename(dest)
                    archived.append(path)

            return {
                "success": True,
                "archived_count": len(archived),
                "archived_paths": archived,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class AlertAgent:
    """Agent that monitors and alerts on memory patterns."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.mem_dir = self.repo_root / ".mem"
        self.alerts_file = self.mem_dir / "alerts.json"
        self._alerts: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """Load alerts from disk."""
        if self.alerts_file.exists():
            try:
                data = json.loads(self.alerts_file.read_text())
                self._alerts = data.get("alerts", [])
            except Exception:
                pass

    def _save(self) -> None:
        """Save alerts to disk."""
        self.mem_dir.mkdir(parents=True, exist_ok=True)
        self.alerts_file.write_text(json.dumps({"alerts": self._alerts}, indent=2))

    def add_alert(
        self,
        alert_type: str,
        message: str,
        severity: str = "info",
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Add a new alert."""
        alert = {
            "id": hashlib.sha256(
                f"{alert_type}{message}{datetime.now().isoformat()}".encode()
            ).hexdigest()[:8],
            "type": alert_type,
            "message": message,
            "severity": severity,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged": False,
            "data": data or {},
        }
        self._alerts.append(alert)
        self._save()
        return alert

    def get_alerts(
        self, unacknowledged_only: bool = False, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get alerts."""
        alerts = self._alerts
        if unacknowledged_only:
            alerts = [a for a in alerts if not a.get("acknowledged")]
        return alerts[-limit:]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        for alert in self._alerts:
            if alert["id"] == alert_id:
                alert["acknowledged"] = True
                alert["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
                self._save()
                return True
        return False

    def check_storage_usage(self, threshold_mb: float = 100) -> Optional[Dict[str, Any]]:
        """Check if storage usage exceeds threshold."""
        from memvcs.core.repository import Repository

        try:
            repo = Repository(self.repo_root)
            current_dir = repo.current_dir

            total_size = 0
            for filepath in current_dir.rglob("*"):
                if filepath.is_file():
                    total_size += filepath.stat().st_size

            size_mb = total_size / (1024 * 1024)
            if size_mb > threshold_mb:
                return self.add_alert(
                    alert_type="storage",
                    message=f"Storage usage ({size_mb:.1f}MB) exceeds threshold ({threshold_mb}MB)",
                    severity="warning",
                    data={"current_mb": size_mb, "threshold_mb": threshold_mb},
                )
        except Exception:
            pass
        return None


class MemoryAgentManager:
    """Manages all memory agents."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.consolidation = ConsolidationAgent(repo_root)
        self.cleanup = CleanupAgent(repo_root)
        self.alert = AlertAgent(repo_root)
        self.rules: List[AgentRule] = []
        self.task_queue: List[AgentTask] = []

    def run_health_check(self) -> Dict[str, Any]:
        """Run a comprehensive health check."""
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {},
        }

        # Check for consolidation candidates
        consolidation_candidates = self.consolidation.find_consolidation_candidates()
        results["checks"]["consolidation"] = {
            "candidate_count": len(consolidation_candidates),
            "candidates": consolidation_candidates[:5],
        }

        # Check for cleanup candidates
        cleanup_candidates = self.cleanup.find_cleanup_candidates(max_age_days=60)
        results["checks"]["cleanup"] = {
            "candidate_count": len(cleanup_candidates),
            "candidates": cleanup_candidates[:5],
        }

        # Check for duplicates
        duplicates = self.cleanup.find_duplicates()
        results["checks"]["duplicates"] = {
            "duplicate_groups": len(duplicates),
            "duplicates": duplicates[:5],
        }

        # Check storage
        storage_alert = self.alert.check_storage_usage(threshold_mb=50)
        results["checks"]["storage"] = {
            "alert": storage_alert is not None,
        }

        # Get recent alerts
        alerts = self.alert.get_alerts(unacknowledged_only=True, limit=10)
        results["alerts"] = alerts

        return results


# --- Dashboard Helper ---


def get_agent_dashboard(repo_root: Path) -> Dict[str, Any]:
    """Get data for memory agent dashboard."""
    manager = MemoryAgentManager(repo_root)
    health = manager.run_health_check()

    return {
        "health_check": health,
        "consolidation_candidates": health["checks"]["consolidation"]["candidate_count"],
        "cleanup_candidates": health["checks"]["cleanup"]["candidate_count"],
        "duplicate_groups": health["checks"]["duplicates"]["duplicate_groups"],
        "unacknowledged_alerts": len(health.get("alerts", [])),
    }
