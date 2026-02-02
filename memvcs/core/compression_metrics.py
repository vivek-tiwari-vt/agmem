"""
Delta compression metrics and observability.

Tracks compression effectiveness across object types to enable future
optimization and auto-tuning of delta encoding parameters.

Provides:
- DeltaCompressionMetrics: Tracks compression ratio, object types, benefits
- CompressionHeatmap: Visualizes which types compress best
- Statistics reporting for gc --repack operations
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict


@dataclass
class ObjectCompressionStats:
    """Statistics for a single object's compression."""

    object_id: str
    object_type: str  # "semantic", "episodic", "procedural"
    original_size: int  # bytes
    compressed_size: int  # bytes after delta encoding
    compression_ratio: float  # compressed_size / original_size (0.0 = 100% compression)
    delta_used: bool  # Whether delta encoding was applied
    compression_benefit: float  # original_size - compressed_size


@dataclass
class TypeCompressionStats:
    """Aggregated statistics for an object type."""

    object_type: str
    count: int = 0
    total_original_size: int = 0
    total_compressed_size: int = 0
    avg_compression_ratio: float = 0.0
    total_benefit: int = 0  # Total bytes saved
    objects_with_delta: int = 0  # How many used delta encoding
    min_ratio: float = 1.0
    max_ratio: float = 0.0

    def update_from_object(self, obj_stats: ObjectCompressionStats) -> None:
        """Update type stats with a single object's stats."""
        self.count += 1
        self.total_original_size += obj_stats.original_size
        self.total_compressed_size += obj_stats.compressed_size
        self.total_benefit += int(obj_stats.compression_benefit)
        if obj_stats.delta_used:
            self.objects_with_delta += 1
        self.min_ratio = min(self.min_ratio, obj_stats.compression_ratio)
        self.max_ratio = max(self.max_ratio, obj_stats.compression_ratio)

        # Recalculate average
        if self.total_original_size > 0:
            self.avg_compression_ratio = self.total_compressed_size / self.total_original_size

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for reporting."""
        savings_pct = 0.0
        if self.total_original_size > 0:
            savings_pct = (self.total_benefit / self.total_original_size) * 100

        return {
            "object_type": self.object_type,
            "count": self.count,
            "total_original_bytes": self.total_original_size,
            "total_compressed_bytes": self.total_compressed_size,
            "avg_compression_ratio": round(self.avg_compression_ratio, 3),
            "compression_range": f"{self.min_ratio:.1%} - {self.max_ratio:.1%}",
            "total_bytes_saved": self.total_benefit,
            "savings_percentage": round(savings_pct, 1),
            "objects_using_delta": self.objects_with_delta,
            "delta_adoption_rate": (
                round((self.objects_with_delta / self.count * 100), 1) if self.count > 0 else 0
            ),
        }


class DeltaCompressionMetrics:
    """Tracks delta compression statistics across all objects.

    Usage:
        metrics = DeltaCompressionMetrics()
        # ... during packing ...
        metrics.record_object(ObjectCompressionStats(...))
        # ... after packing ...
        report = metrics.get_report()
    """

    def __init__(self):
        self.objects: List[ObjectCompressionStats] = []
        self.type_stats: Dict[str, TypeCompressionStats] = {}
        self.total_original_size: int = 0
        self.total_compressed_size: int = 0

    def record_object(self, obj_stats: ObjectCompressionStats) -> None:
        """Record compression stats for a single object."""
        self.objects.append(obj_stats)
        self.total_original_size += obj_stats.original_size
        self.total_compressed_size += obj_stats.compressed_size

        # Update type-specific stats
        if obj_stats.object_type not in self.type_stats:
            self.type_stats[obj_stats.object_type] = TypeCompressionStats(
                object_type=obj_stats.object_type
            )
        self.type_stats[obj_stats.object_type].update_from_object(obj_stats)

    def get_type_stats(self, object_type: str) -> Optional[TypeCompressionStats]:
        """Get stats for a specific object type."""
        return self.type_stats.get(object_type)

    def get_overall_ratio(self) -> float:
        """Get overall compression ratio across all objects."""
        if self.total_original_size == 0:
            return 0.0
        return self.total_compressed_size / self.total_original_size

    def get_overall_savings(self) -> int:
        """Get total bytes saved across all objects."""
        return self.total_original_size - self.total_compressed_size

    def get_report(self) -> Dict[str, Any]:
        """Generate a comprehensive compression report."""
        overall_ratio = self.get_overall_ratio()
        overall_savings = self.get_overall_savings()
        savings_pct = (
            (overall_savings / self.total_original_size * 100)
            if self.total_original_size > 0
            else 0
        )

        return {
            "timestamp": None,  # Set by caller if needed
            "total_objects": len(self.objects),
            "total_original_bytes": self.total_original_size,
            "total_compressed_bytes": self.total_compressed_size,
            "overall_compression_ratio": round(overall_ratio, 3),
            "total_bytes_saved": overall_savings,
            "compression_percentage": round(savings_pct, 1),
            "type_statistics": {otype: stats.to_dict() for otype, stats in self.type_stats.items()},
            "recommendations": self._generate_recommendations(),
        }

    def _generate_recommendations(self) -> List[str]:
        """Generate optimization recommendations based on compression stats."""
        recommendations = []

        # Check if delta encoding is worth it
        objects_with_delta = sum(s.objects_with_delta for s in self.type_stats.values())
        if objects_with_delta == 0:
            recommendations.append("No objects used delta encoding. Check similarity thresholds.")

        # Check for types with poor compression
        for otype, stats in self.type_stats.items():
            if stats.count > 0 and stats.avg_compression_ratio > 0.9:
                recommendations.append(
                    f"Type '{otype}' compresses poorly (ratio: {stats.avg_compression_ratio:.1%}). "
                    f"Consider increasing similarity threshold or reducing delta cost."
                )

        # Check for types with excellent compression
        for otype, stats in self.type_stats.items():
            if stats.count > 0 and stats.avg_compression_ratio < 0.5:
                recommendations.append(
                    f"Type '{otype}' compresses very well (ratio: {stats.avg_compression_ratio:.1%}). "
                    f"Consider aggressive delta encoding or reduced threshold."
                )

        if not recommendations:
            recommendations.append("Compression is operating normally.")

        return recommendations

    def get_heatmap(self) -> str:
        """Generate a text-based compression heatmap."""
        lines = ["Delta Compression Heatmap", "=" * 50]

        if not self.type_stats:
            lines.append("No compression data available")
            return "\n".join(lines)

        # Sort by compression ratio
        sorted_types = sorted(
            self.type_stats.values(),
            key=lambda s: s.avg_compression_ratio,
        )

        for stats in sorted_types:
            if stats.count == 0:
                continue
            ratio = stats.avg_compression_ratio
            # Create a simple bar chart
            bar_width = 30
            filled = int(bar_width * ratio)
            bar = "█" * filled + "░" * (bar_width - filled)
            saved_pct = (
                (stats.total_benefit / stats.total_original_size * 100)
                if stats.total_original_size > 0
                else 0
            )
            lines.append(
                f"{stats.object_type:12} {bar} {saved_pct:5.1f}% saved ({stats.objects_with_delta}/{stats.count} using delta)"
            )

        return "\n".join(lines)

    def log_report(self, logger: Any = None) -> None:
        """Log the compression report."""
        report = self.get_report()
        heatmap = self.get_heatmap()

        output = [
            "=" * 70,
            "Delta Compression Report",
            "=" * 70,
            f"Total Objects: {report['total_objects']}",
            f"Total Original: {report['total_original_bytes']:,} bytes",
            f"Total Compressed: {report['total_compressed_bytes']:,} bytes",
            f"Overall Ratio: {report['overall_compression_ratio']:.1%}",
            f"Bytes Saved: {report['total_bytes_saved']:,} ({report['compression_percentage']:.1f}%)",
            "",
            heatmap,
            "",
            "Type Breakdown:",
        ]

        for otype, stats in sorted(report["type_statistics"].items()):
            output.append(f"  {otype}:")
            output.append(f"    Count: {stats['count']}")
            output.append(f"    Compression: {stats['avg_compression_ratio']:.1%}")
            output.append(f"    Saved: {stats['total_bytes_saved']:,} bytes")
            output.append(f"    Delta adoption: {stats['delta_adoption_rate']:.0f}%")

        output.extend(["", "Recommendations:"])
        for rec in report["recommendations"]:
            output.append(f"  - {rec}")

        output.append("=" * 70)

        full_output = "\n".join(output)
        if logger:
            logger.info(full_output)
        else:
            print(full_output)
