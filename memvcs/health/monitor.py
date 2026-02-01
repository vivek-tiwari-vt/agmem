"""
Health monitoring for agmem daemon.

Periodic checks for repository health:
- Storage metrics (size, growth rate)
- Semantic redundancy detection
- Stale memory detection
- Knowledge graph consistency
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple


@dataclass
class StorageMetrics:
    """Repository storage metrics."""

    total_size_bytes: int
    objects_size_bytes: int
    pack_size_bytes: int
    loose_objects_count: int
    packed_objects_count: int
    growth_rate_per_hour: float  # bytes per hour
    warning: Optional[str] = None


@dataclass
class RedundancyReport:
    """Semantic redundancy analysis."""

    total_files: int
    total_size_bytes: int
    duplicate_hashes: Dict[str, List[str]]  # hash -> [file paths]
    redundancy_percentage: float
    similar_files: List[Tuple[str, str, float]]  # (file1, file2, similarity 0-1)
    warning: Optional[str] = None


@dataclass
class StaleMemoryReport:
    """Stale/unused memory detection."""

    total_files: int
    stale_files: List[Dict[str, Any]]  # {path, days_unaccessed, size_bytes}
    stale_percentage: float
    warning: Optional[str] = None


@dataclass
class GraphConsistencyReport:
    """Knowledge graph integrity check."""

    total_nodes: int
    total_edges: int
    orphaned_nodes: List[str]
    dangling_edges: List[Tuple[str, str]]  # (source, target)
    contradictions: List[Dict[str, Any]]
    warning: Optional[str] = None


class StorageMonitor:
    """Monitor repository storage growth and usage."""

    def __init__(self, mem_dir: Path):
        self.mem_dir = mem_dir
        self.objects_dir = mem_dir / "objects"
        self.pack_dir = self.objects_dir / "pack"
        self.metrics_file = mem_dir / ".health" / "storage_metrics.json"

    def get_metrics(self) -> StorageMetrics:
        """Compute current storage metrics."""
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

        # Calculate object sizes
        objects_size = self._dir_size(self.objects_dir)
        pack_size = self._dir_size(self.pack_dir) if self.pack_dir.exists() else 0
        loose_size = objects_size - pack_size

        # Count objects
        loose_count = self._count_objects(self.objects_dir, "loose")
        pack_count = self._count_objects(self.objects_dir, "packed")

        # Calculate growth rate
        growth_rate = self._calculate_growth_rate(objects_size)

        warning = None
        if objects_size > 5 * 1024 * 1024 * 1024:  # 5GB
            warning = "Repository exceeds 5GB - consider archival or splitting"

        return StorageMetrics(
            total_size_bytes=objects_size,
            objects_size_bytes=objects_size,
            pack_size_bytes=pack_size,
            loose_objects_count=loose_count,
            packed_objects_count=pack_count,
            growth_rate_per_hour=growth_rate,
            warning=warning,
        )

    def _dir_size(self, path: Path) -> int:
        """Recursively sum directory size."""
        if not path.exists():
            return 0
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    pass
        return total

    def _count_objects(self, obj_dir: Path, obj_type: str) -> int:
        """Count objects by type."""
        if not obj_dir.exists():
            return 0
        count = 0
        for type_dir in ["blob", "tree", "commit", "tag"]:
            type_path = obj_dir / type_dir
            if type_path.exists():
                for item in type_path.rglob("*"):
                    if item.is_file():
                        count += 1
        return count

    def _calculate_growth_rate(self, current_size: int) -> float:
        """Calculate bytes/hour growth rate from historical data."""
        try:
            metrics_data = json.loads(self.metrics_file.read_text())
            prev_size = metrics_data.get("total_size_bytes", current_size)
            prev_time = metrics_data.get("timestamp")
            if prev_time:
                hours_elapsed = (datetime.now(timezone.utc).timestamp() - prev_time) / 3600
                if hours_elapsed > 0:
                    rate = (current_size - prev_size) / hours_elapsed
                    return max(0, rate)
        except Exception:
            pass

        # Store current metrics for next check
        try:
            json.dump(
                {
                    "total_size_bytes": current_size,
                    "timestamp": datetime.now(timezone.utc).timestamp(),
                },
                open(self.metrics_file, "w"),
            )
        except Exception:
            pass

        return 0.0


class SemanticRedundancyChecker:
    """Detect duplicate and similar semantic memories."""

    def __init__(self, current_dir: Path):
        self.current_dir = current_dir
        self.semantic_dir = current_dir / "semantic"

    def check_redundancy(self) -> RedundancyReport:
        """Check for content and semantic redundancy."""
        if not self.semantic_dir.exists():
            return RedundancyReport(
                total_files=0,
                total_size_bytes=0,
                duplicate_hashes={},
                redundancy_percentage=0.0,
                similar_files=[],
            )

        files = list(self.semantic_dir.rglob("*.md"))
        if not files:
            return RedundancyReport(
                total_files=0,
                total_size_bytes=0,
                duplicate_hashes={},
                redundancy_percentage=0.0,
                similar_files=[],
            )

        # Hash-based deduplication
        hash_map: Dict[str, List[str]] = {}
        total_size = 0

        for fpath in files:
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                content_hash = hashlib.sha256(content.encode()).hexdigest()
                hash_map.setdefault(content_hash, []).append(
                    str(fpath.relative_to(self.current_dir))
                )
                total_size += len(content.encode())
            except Exception:
                pass

        # Find duplicates
        duplicates = {h: paths for h, paths in hash_map.items() if len(paths) > 1}

        # Calculate redundancy: measure wasted space from duplicates
        # For each duplicate set, count all but the first as redundant
        duplicate_waste_size = 0
        file_sizes = {}

        for fpath in files:
            try:
                rel_path = str(fpath.relative_to(self.current_dir))
                file_sizes[rel_path] = fpath.stat().st_size
            except (OSError, TypeError):
                pass

        for hash_val, paths in duplicates.items():
            if len(paths) > 1:
                # All copies except the first are redundant
                for dup_path in paths[1:]:
                    duplicate_waste_size += file_sizes.get(dup_path, 0)

        redundancy_pct = (duplicate_waste_size / total_size * 100) if total_size > 0 else 0

        warning = None
        if redundancy_pct > 20:
            warning = f"High semantic redundancy ({redundancy_pct:.1f}%) - consolidate memories"

        return RedundancyReport(
            total_files=len(files),
            total_size_bytes=total_size,
            duplicate_hashes=duplicates,
            redundancy_percentage=redundancy_pct,
            similar_files=[],
            warning=warning,
        )


class StaleMemoryDetector:
    """Detect unused/stale memories."""

    def __init__(self, current_dir: Path):
        self.current_dir = current_dir
        self.stale_threshold_days = 90

    def detect_stale(self) -> StaleMemoryReport:
        """Find memories not accessed in threshold period."""
        files = list(self.current_dir.rglob("*.md"))
        if not files:
            return StaleMemoryReport(
                total_files=0,
                stale_files=[],
                stale_percentage=0.0,
            )

        now = datetime.now(timezone.utc).timestamp()
        stale_list = []
        total_size = 0

        for fpath in files:
            try:
                stat = fpath.stat()
                age_days = (now - stat.st_atime) / 86400
                total_size += stat.st_size

                if age_days > self.stale_threshold_days:
                    stale_list.append(
                        {
                            "path": str(fpath.relative_to(self.current_dir)),
                            "days_unaccessed": int(age_days),
                            "size_bytes": stat.st_size,
                        }
                    )
            except Exception:
                pass

        stale_pct = (len(stale_list) / len(files) * 100) if files else 0

        warning = None
        if stale_pct > 30:
            warning = f"High stale memory percentage ({stale_pct:.1f}%) - consider archival"

        return StaleMemoryReport(
            total_files=len(files),
            stale_files=sorted(stale_list, key=lambda x: x["days_unaccessed"], reverse=True),
            stale_percentage=stale_pct,
            warning=warning,
        )


class GraphConsistencyValidator:
    """Validate knowledge graph integrity."""

    def __init__(self, current_dir: Path):
        self.current_dir = current_dir

    def validate_graph(self) -> GraphConsistencyReport:
        """Check graph for orphaned nodes, dangling edges, contradictions."""
        try:
            import re
        except ImportError:
            return GraphConsistencyReport(
                total_nodes=0,
                total_edges=0,
                orphaned_nodes=[],
                dangling_edges=[],
                contradictions=[],
            )

        semantic_dir = self.current_dir / "semantic"
        if not semantic_dir.exists():
            return GraphConsistencyReport(
                total_nodes=0,
                total_edges=0,
                orphaned_nodes=[],
                dangling_edges=[],
                contradictions=[],
            )

        # Extract all nodes (files) and edges (wikilinks)
        nodes = set()
        edges = []
        contradictions = []

        for fpath in semantic_dir.rglob("*.md"):
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                node_name = fpath.stem

                nodes.add(node_name)

                # Find wikilinks: [[target]], [[target|label]]
                wikilinks = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)
                for target in wikilinks:
                    edges.append((node_name, target.strip()))

                # Find conflict markers (potential contradictions)
                if "<<<<<" in content or "=====" in content or ">>>>>" in content:
                    contradictions.append(
                        {
                            "file": str(fpath.relative_to(self.current_dir)),
                            "type": "unresolved_merge_conflict",
                        }
                    )
            except Exception:
                pass

        # Find dangling edges (edges to non-existent nodes)
        dangling = [(src, tgt) for src, tgt in edges if tgt not in nodes]

        # Find orphaned nodes (nodes with no edges)
        nodes_with_edges = set(src for src, _ in edges) | set(tgt for _, tgt in edges)
        orphaned = list(nodes - nodes_with_edges)

        warning = None
        if dangling:
            warning = f"Graph has {len(dangling)} dangling edge(s) - fix broken links"
        if orphaned:
            warning = (warning or "") + f" {len(orphaned)} orphaned node(s) - no connections"
        if contradictions:
            warning = (warning or "") + f" {len(contradictions)} conflict marker(s)"

        return GraphConsistencyReport(
            total_nodes=len(nodes),
            total_edges=len(edges),
            orphaned_nodes=orphaned,
            dangling_edges=dangling,
            contradictions=contradictions,
            warning=warning.strip() if warning else None,
        )


class HealthMonitor:
    """Orchestrate all health checks."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.mem_dir = repo_path / ".mem"
        self.current_dir = repo_path / "current"

    def perform_all_checks(self) -> Dict[str, Any]:
        """Run all health checks and return comprehensive report."""
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "storage": None,
            "redundancy": None,
            "stale_memory": None,
            "graph_consistency": None,
            "warnings": [],
        }

        # Storage check
        try:
            storage_monitor = StorageMonitor(self.mem_dir)
            metrics = storage_monitor.get_metrics()
            report["storage"] = {
                "total_size_mb": metrics.total_size_bytes / 1024 / 1024,
                "loose_objects": metrics.loose_objects_count,
                "packed_objects": metrics.packed_objects_count,
                "growth_rate_mb_per_hour": metrics.growth_rate_per_hour / 1024 / 1024,
            }
            if metrics.warning:
                report["warnings"].append(metrics.warning)
        except Exception as e:
            report["storage"] = {"error": str(e)}

        # Redundancy check
        try:
            redundancy = SemanticRedundancyChecker(self.current_dir)
            red_report = redundancy.check_redundancy()
            report["redundancy"] = {
                "total_files": red_report.total_files,
                "duplicates_found": len(red_report.duplicate_hashes),
                "redundancy_percentage": red_report.redundancy_percentage,
            }
            if red_report.warning:
                report["warnings"].append(red_report.warning)
        except Exception as e:
            report["redundancy"] = {"error": str(e)}

        # Stale memory check
        try:
            stale_detector = StaleMemoryDetector(self.current_dir)
            stale_report = stale_detector.detect_stale()
            report["stale_memory"] = {
                "total_files": stale_report.total_files,
                "stale_files": len(stale_report.stale_files),
                "stale_percentage": stale_report.stale_percentage,
            }
            if stale_report.warning:
                report["warnings"].append(stale_report.warning)
        except Exception as e:
            report["stale_memory"] = {"error": str(e)}

        # Graph consistency check
        try:
            graph_validator = GraphConsistencyValidator(self.current_dir)
            graph_report = graph_validator.validate_graph()
            report["graph_consistency"] = {
                "total_nodes": graph_report.total_nodes,
                "total_edges": graph_report.total_edges,
                "orphaned_nodes": len(graph_report.orphaned_nodes),
                "dangling_edges": len(graph_report.dangling_edges),
                "contradictions": len(graph_report.contradictions),
            }
            if graph_report.warning:
                report["warnings"].append(graph_report.warning)
        except Exception as e:
            report["graph_consistency"] = {"error": str(e)}

        return report
