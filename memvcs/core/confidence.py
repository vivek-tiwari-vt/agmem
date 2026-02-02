"""
Confidence Scoring - Memory reliability with temporal decay.

This module provides:
- Confidence scoring for memories
- Temporal decay calculations
- Source reliability tracking
- Evidence chain analysis
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ConfidenceFactors:
    """Factors that contribute to confidence score."""

    source_reliability: float = 1.0  # 0.0 to 1.0
    corroboration_count: int = 0  # Number of supporting sources
    age_days: float = 0.0  # Age in days
    access_frequency: int = 0  # How often accessed
    last_verified: Optional[str] = None
    contradiction_count: int = 0  # Number of conflicting sources


@dataclass
class ConfidenceScore:
    """A confidence score for a memory."""

    score: float  # 0.0 to 1.0
    factors: ConfidenceFactors
    decay_rate: float  # Daily decay rate
    computed_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "factors": {
                "source_reliability": self.factors.source_reliability,
                "corroboration_count": self.factors.corroboration_count,
                "age_days": round(self.factors.age_days, 1),
                "access_frequency": self.factors.access_frequency,
                "contradiction_count": self.factors.contradiction_count,
            },
            "decay_rate": self.decay_rate,
            "computed_at": self.computed_at,
        }


class DecayModel:
    """Models confidence decay over time."""

    # Decay models
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    STEP = "step"

    def __init__(self, model: str = EXPONENTIAL, half_life_days: float = 30.0):
        self.model = model
        self.half_life_days = half_life_days

    def calculate_decay(self, age_days: float) -> float:
        """Calculate decay factor (0.0 to 1.0) based on age."""
        if age_days <= 0:
            return 1.0

        if self.model == self.EXPONENTIAL:
            # Exponential decay with half-life
            decay_constant = math.log(2) / self.half_life_days
            return math.exp(-decay_constant * age_days)

        elif self.model == self.LINEAR:
            # Linear decay over 2x half-life
            max_age = self.half_life_days * 2
            return max(0.0, 1.0 - (age_days / max_age))

        elif self.model == self.STEP:
            # Step function at half-life
            if age_days < self.half_life_days:
                return 1.0
            elif age_days < self.half_life_days * 2:
                return 0.5
            else:
                return 0.2

        return 1.0

    def days_until_threshold(self, current_score: float, threshold: float) -> Optional[float]:
        """Calculate days until score drops below threshold."""
        if current_score <= threshold:
            return 0.0

        if self.model == self.EXPONENTIAL:
            decay_constant = math.log(2) / self.half_life_days
            return math.log(current_score / threshold) / decay_constant

        elif self.model == self.LINEAR:
            max_age = self.half_life_days * 2
            return max_age * (current_score - threshold)

        return None


class SourceTracker:
    """Tracks source reliability."""

    def __init__(self, mem_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.sources_file = self.mem_dir / "sources.json"
        self._sources: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load sources from disk."""
        if self.sources_file.exists():
            try:
                data = json.loads(self.sources_file.read_text())
                self._sources = data.get("sources", {})
            except Exception:
                pass

    def _save(self) -> None:
        """Save sources to disk."""
        self.mem_dir.mkdir(parents=True, exist_ok=True)
        self.sources_file.write_text(json.dumps({"sources": self._sources}, indent=2))

    def register_source(
        self,
        source_id: str,
        name: str,
        initial_reliability: float = 0.8,
        source_type: str = "agent",
    ) -> Dict[str, Any]:
        """Register a new source."""
        self._sources[source_id] = {
            "name": name,
            "reliability": initial_reliability,
            "type": source_type,
            "contributions": 0,
            "verified_count": 0,
            "error_count": 0,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()
        return self._sources[source_id]

    def get_reliability(self, source_id: str) -> float:
        """Get reliability score for a source."""
        source = self._sources.get(source_id)
        if not source:
            return 0.5  # Unknown source default
        return source.get("reliability", 0.5)

    def update_reliability(self, source_id: str, delta: float) -> float:
        """Update source reliability by delta."""
        source = self._sources.get(source_id)
        if source:
            new_reliability = max(0.1, min(1.0, source["reliability"] + delta))
            source["reliability"] = new_reliability
            self._save()
            return new_reliability
        return 0.5

    def record_verification(self, source_id: str, verified: bool) -> None:
        """Record a verification result for a source."""
        source = self._sources.get(source_id)
        if source:
            if verified:
                source["verified_count"] = source.get("verified_count", 0) + 1
                self.update_reliability(source_id, 0.01)
            else:
                source["error_count"] = source.get("error_count", 0) + 1
                self.update_reliability(source_id, -0.05)

    def get_all_sources(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered sources."""
        return self._sources.copy()


class ConfidenceCalculator:
    """Calculates confidence scores for memories."""

    def __init__(
        self,
        mem_dir: Path,
        decay_model: Optional[DecayModel] = None,
    ):
        self.mem_dir = Path(mem_dir)
        self.decay_model = decay_model or DecayModel()
        self.source_tracker = SourceTracker(mem_dir)
        self.scores_file = self.mem_dir / "confidence_scores.json"
        self._scores: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load scores from disk."""
        if self.scores_file.exists():
            try:
                data = json.loads(self.scores_file.read_text())
                self._scores = data.get("scores", {})
            except Exception:
                pass

    def _save(self) -> None:
        """Save scores to disk."""
        self.mem_dir.mkdir(parents=True, exist_ok=True)
        self.scores_file.write_text(json.dumps({"scores": self._scores}, indent=2))

    def calculate_score(
        self,
        path: str,
        source_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> ConfidenceScore:
        """Calculate confidence score for a memory."""
        # Get source reliability
        source_reliability = 0.8
        if source_id:
            source_reliability = self.source_tracker.get_reliability(source_id)

        # Calculate age
        age_days = 0.0
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - created_dt).total_seconds() / 86400
            except Exception:
                pass

        # Get existing score data for corroboration/contradiction
        existing = self._scores.get(path, {})
        corroboration_count = existing.get("corroboration_count", 0)
        contradiction_count = existing.get("contradiction_count", 0)
        access_frequency = existing.get("access_count", 0)

        factors = ConfidenceFactors(
            source_reliability=source_reliability,
            corroboration_count=corroboration_count,
            age_days=age_days,
            access_frequency=access_frequency,
            contradiction_count=contradiction_count,
        )

        # Calculate base score
        base_score = source_reliability

        # Apply corroboration boost
        corroboration_boost = min(0.2, corroboration_count * 0.05)
        base_score = min(1.0, base_score + corroboration_boost)

        # Apply contradiction penalty
        contradiction_penalty = min(0.3, contradiction_count * 0.1)
        base_score = max(0.0, base_score - contradiction_penalty)

        # Apply time decay
        decay_factor = self.decay_model.calculate_decay(age_days)
        final_score = base_score * decay_factor

        score = ConfidenceScore(
            score=final_score,
            factors=factors,
            decay_rate=math.log(2) / self.decay_model.half_life_days,
            computed_at=datetime.now(timezone.utc).isoformat(),
        )

        # Store score
        self._scores[path] = {
            **factors.__dict__,
            "score": final_score,
            "computed_at": score.computed_at,
        }
        self._save()

        return score

    def get_score(self, path: str) -> Optional[ConfidenceScore]:
        """Get stored confidence score."""
        stored = self._scores.get(path)
        if not stored:
            return None

        factors = ConfidenceFactors(
            source_reliability=stored.get("source_reliability", 0.8),
            corroboration_count=stored.get("corroboration_count", 0),
            age_days=stored.get("age_days", 0),
            access_frequency=stored.get("access_frequency", 0),
            contradiction_count=stored.get("contradiction_count", 0),
        )

        return ConfidenceScore(
            score=stored.get("score", 0.5),
            factors=factors,
            decay_rate=stored.get("decay_rate", 0.023),
            computed_at=stored.get("computed_at", ""),
        )

    def add_corroboration(self, path: str) -> None:
        """Add corroborating evidence for a memory."""
        if path in self._scores:
            self._scores[path]["corroboration_count"] = (
                self._scores[path].get("corroboration_count", 0) + 1
            )
            self._save()

    def add_contradiction(self, path: str) -> None:
        """Add contradicting evidence for a memory."""
        if path in self._scores:
            self._scores[path]["contradiction_count"] = (
                self._scores[path].get("contradiction_count", 0) + 1
            )
            self._save()

    def record_access(self, path: str) -> None:
        """Record an access to a memory."""
        if path not in self._scores:
            self._scores[path] = {}
        self._scores[path]["access_count"] = self._scores[path].get("access_count", 0) + 1
        self._save()

    def get_low_confidence_memories(self, threshold: float = 0.5) -> List[Dict[str, Any]]:
        """Get memories with low confidence scores."""
        low_confidence = []
        for path, data in self._scores.items():
            if data.get("score", 1.0) < threshold:
                low_confidence.append(
                    {
                        "path": path,
                        "score": data.get("score"),
                        "age_days": data.get("age_days", 0),
                    }
                )

        return sorted(low_confidence, key=lambda x: x["score"])

    def get_expiring_soon(self, days: int = 7, threshold: float = 0.5) -> List[Dict[str, Any]]:
        """Get memories that will fall below threshold soon."""
        expiring = []
        for path, data in self._scores.items():
            current_score = data.get("score", 1.0)
            if current_score > threshold:
                days_until = self.decay_model.days_until_threshold(current_score, threshold)
                if days_until and days_until <= days:
                    expiring.append(
                        {
                            "path": path,
                            "current_score": current_score,
                            "days_until_threshold": round(days_until, 1),
                        }
                    )

        return sorted(expiring, key=lambda x: x["days_until_threshold"])


# --- Dashboard Helper ---


def get_confidence_dashboard(mem_dir: Path) -> Dict[str, Any]:
    """Get data for confidence scoring dashboard."""
    calculator = ConfidenceCalculator(mem_dir)
    source_tracker = SourceTracker(mem_dir)

    low_confidence = calculator.get_low_confidence_memories(threshold=0.5)
    expiring = calculator.get_expiring_soon(days=7, threshold=0.5)
    sources = source_tracker.get_all_sources()

    return {
        "low_confidence_count": len(low_confidence),
        "low_confidence_memories": low_confidence[:10],
        "expiring_soon_count": len(expiring),
        "expiring_soon": expiring[:10],
        "sources": list(sources.values()),
        "source_count": len(sources),
    }
