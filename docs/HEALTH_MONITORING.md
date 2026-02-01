# Health Monitoring System

Comprehensive health monitoring for the agmem daemon to track repository operational status and detect issues early.

## Overview

The health monitoring system performs periodic checks on the repository to ensure:
- **Storage integrity** - Track object count, size, growth rate
- **Semantic health** - Detect duplicate/redundant memories
- **Memory staleness** - Identify unused memories for archival
- **Graph consistency** - Validate wikilink graph and detect corruption

## Components

### StorageMonitor

Tracks repository storage metrics with growth rate analysis.

**Metrics Provided:**
- `total_size_bytes` - Total objects directory size
- `objects_size_bytes` - Size of all objects (loose + packed)
- `pack_size_bytes` - Size of packed objects
- `loose_objects_count` - Number of unpacked objects
- `packed_objects_count` - Number of objects in pack files
- `growth_rate_per_hour` - Historical growth rate in bytes/hour
- `warning` - Alert if exceeds 5GB threshold

**Use Case:** Monitor storage growth to plan capacity, identify bloat before crisis.

```python
from memvcs.health.monitor import StorageMonitor
from pathlib import Path

monitor = StorageMonitor(Path(".mem"))
metrics = monitor.get_metrics()
print(f"Storage: {metrics.total_size_bytes / 1024**3:.1f}GB")
print(f"Growth: {metrics.growth_rate_per_hour / 1024**2:.1f}MB/hour")
```

### SemanticRedundancyChecker

Detects duplicate and similar semantic memories.

**Analysis:**
- **Duplicate Detection** - SHA-256 hashing of file contents
- **Redundancy Percentage** - Percentage of wasted space from duplicates
- **Similar Files** - Extensible for semantic similarity (future: embeddings-based)

**Warnings:**
- Triggers if redundancy > 20%

**Use Case:** Identify consolidation opportunities, prevent memory explosion.

```python
from memvcs.health.monitor import SemanticRedundancyChecker

checker = SemanticRedundancyChecker(Path("current"))
report = checker.check_redundancy()
print(f"Duplicates: {len(report.duplicate_hashes)}")
print(f"Wasted space: {report.redundancy_percentage:.1f}%")
```

### StaleMemoryDetector

Identifies memories not accessed within a threshold period (default: 90 days).

**Analysis:**
- **Stale Detection** - Uses file access time (mtime)
- **Stale Percentage** - Proportion of repository that's unused
- **Detailed List** - Per-file age and size information

**Warnings:**
- Triggers if stale > 30%

**Use Case:** Archive old memories, reduce active working set.

```python
from memvcs.health.monitor import StaleMemoryDetector

detector = StaleMemoryDetector(Path("current"))
report = detector.detect_stale()
for stale in report.stale_files[:5]:
    print(f"{stale['path']}: {stale['days_unaccessed']}d old")
```

### GraphConsistencyValidator

Validates knowledge graph integrity by checking wikilink references.

**Validation Checks:**
- **Dangling Edges** - References to non-existent nodes `[[target]]`
- **Orphaned Nodes** - Files with no wikilinks in/out
- **Conflict Markers** - Unresolved merge conflicts (`<<<<< HEAD`, `=====`, `>>>>>`)
- **Graph Stats** - Total nodes and edges

**Warnings:**
- Triggers for any dangling edges, orphaned nodes, or conflicts

**Use Case:** Detect broken links, unresolved merges before they accumulate.

```python
from memvcs.health.monitor import GraphConsistencyValidator

validator = GraphConsistencyValidator(Path("current"))
report = validator.validate_graph()
print(f"Nodes: {report.total_nodes}, Edges: {report.total_edges}")
print(f"Dangling: {report.dangling_edges}")
```

### HealthMonitor

Orchestrates all health checks and produces comprehensive report.

**Report Structure:**
```python
{
    "timestamp": "2024-01-15T10:30:00+00:00",
    "storage": {
        "total_size_mb": 512.5,
        "loose_objects": 1200,
        "packed_objects": 800,
        "growth_rate_mb_per_hour": 2.3
    },
    "redundancy": {
        "total_files": 5000,
        "duplicates_found": 45,
        "redundancy_percentage": 8.5
    },
    "stale_memory": {
        "total_files": 5000,
        "stale_files": 200,
        "stale_percentage": 4.0
    },
    "graph_consistency": {
        "total_nodes": 5000,
        "total_edges": 8500,
        "orphaned_nodes": 50,
        "dangling_edges": 12,
        "contradictions": 0
    },
    "warnings": [
        "Graph has 12 dangling edge(s) - fix broken links",
        "50 orphaned node(s) - no connections"
    ]
}
```

**Use Case:** Get complete health snapshot for monitoring dashboards.

```python
from memvcs.health.monitor import HealthMonitor

monitor = HealthMonitor(Path("."))
report = monitor.perform_all_checks()
for warning in report["warnings"]:
    print(f"⚠️  {warning}")
```

## Daemon Integration

The health monitoring system is integrated into the daemon's periodic health check loop (configurable interval, default: 1 hour).

### Configuration

Edit `.agmem/config.yaml`:

```yaml
daemon:
  health_check_interval_seconds: 3600  # 1 hour (0 to disable)
```

Or set environment variable:
```bash
export AGMEM_DAEMON_HEALTH_INTERVAL=1800  # 30 minutes
```

### Output

Health checks run in background without blocking commits. Warnings are logged to stderr:

```
Health warning: High semantic redundancy (45.2%) - consolidate memories
Storage: 512.5MB (800 packed objects)
Redundancy: 8.5%
Stale memory: 4.0%
```

## Performance

- **Storage check:** O(n) directory traversal, typically <100ms
- **Redundancy check:** O(n) SHA-256 hashing, typically <500ms for 5000 files
- **Stale detection:** O(n) stat calls, typically <200ms
- **Graph validation:** O(n) regex parsing, typically <300ms for 5000 files
- **Total:** ~1-2 seconds for complete repository scan

## Best Practices

### Responding to Warnings

**High Redundancy (>20%)**
1. Review duplicate sets in `duplicate_hashes`
2. Consolidate similar episodes into semantic memories
3. Run distillation to normalize facts

**High Staleness (>30%)**
1. Review stale file list for candidates
2. Archive old memories: `agmem archive --older-than 180`
3. Consider splitting repository by time periods

**Graph Inconsistencies**
1. Fix dangling edges: `agmem repair --links`
2. Resolve merge conflicts manually
3. Review orphaned nodes for relevance

**Storage Growth**
1. Check growth rate trend
2. Run garbage collection: `agmem gc`
3. Consider incremental backup strategy

### Customizing Thresholds

Modify checker thresholds in `memvcs/health/monitor.py`:

```python
class StorageMonitor:
    LARGE_REPO_THRESHOLD = 5 * 1024**3  # Change from 5GB

class SemanticRedundancyChecker:
    HIGH_REDUNDANCY_THRESHOLD = 25  # Change from 20%

class StaleMemoryDetector:
    stale_threshold_days = 120  # Change from 90
    HIGH_STALE_THRESHOLD = 35  # Change from 30%
```

## Testing

Run health monitoring tests:

```bash
pytest tests/test_health_monitor.py -v
```

Test coverage includes:
- Storage metrics calculation and growth rate tracking
- Redundancy detection with edge cases
- Stale memory detection with access time manipulation
- Graph validation for cycles, orphans, conflicts
- Error resilience in all checkers

## Future Enhancements

1. **Semantic Similarity** - Embeddings-based duplicate detection
2. **Predictive Alerts** - ML-based growth projection
3. **Health Scoring** - Overall repository health 0-100 metric
4. **Auto-Remediation** - Automatic GC, archive, dedup when thresholds exceeded
5. **Metrics Export** - Prometheus-compatible metrics for monitoring

## Related Commands

- `agmem gc` - Garbage collection
- `agmem distill` - Consolidate episodic to semantic
- `agmem fsck` - Deep integrity check
- `agmem archive` - Move old memories
- `agmem repair` - Fix detected issues
