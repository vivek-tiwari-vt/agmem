"""
Decay engine - memory decay and forgetting for agmem.

Mimics human forgetting: irrelevant details fade, important ones strengthen.
Ebbinghaus-inspired time decay + retrieval-induced enhancement.
"""

import math
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .constants import MEMORY_TYPES
from .access_index import AccessIndex
from .objects import Commit
from .schema import FrontmatterParser


@dataclass
class DecayConfig:
    """Configuration for decay engine."""

    episodic_half_life_days: int = 30
    semantic_min_importance: float = 0.3
    access_count_threshold: int = 2
    forgetting_dir: str = "forgetting"


@dataclass
class DecayCandidate:
    """A memory candidate for decay (archiving)."""

    path: str
    memory_type: str
    importance: float
    last_access_days: Optional[float]
    access_count: int
    decay_score: float
    reason: str


class DecayEngine:
    """Computes decay scores and archives low-importance memories."""

    def __init__(self, repo: Any, config: Optional[DecayConfig] = None):
        self.repo = repo
        self.config = config or DecayConfig()
        self.access_index = AccessIndex(repo.mem_dir)
        self.forgetting_dir = repo.mem_dir / self.config.forgetting_dir
        self.current_dir = repo.current_dir

    def _get_importance(self, path: str, content: str) -> float:
        """Get importance from frontmatter or default."""
        fm, _ = FrontmatterParser.parse(content)
        if fm and fm.importance is not None:
            return float(fm.importance)
        if fm and fm.confidence_score is not None:
            return float(fm.confidence_score)
        return 0.5

    def _get_access_info(self, path: str) -> Tuple[int, Optional[float]]:
        """Get access count and days since last access."""
        counts = self.access_index.get_access_counts_by_path()
        count = counts.get(path, 0)
        recent = self.access_index.get_recent_accesses(limit=1, path=path)
        if not recent:
            return count, None
        ts_str = recent[0].get("timestamp", "")
        if not ts_str:
            return count, None
        try:
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            last = datetime.fromisoformat(ts_str)
            days = (datetime.utcnow() - last.replace(tzinfo=None)).total_seconds() / 86400
            return count, days
        except Exception:
            return count, None

    def compute_decay_score(
        self,
        path: str,
        content: str,
        memory_type: str,
    ) -> DecayCandidate:
        """
        Compute decay score for a memory.

        Higher score = more likely to decay (archive).
        Time decay: importance * 0.5^(days/half_life) when never accessed.
        Retrieval-induced enhancement: access boosts strength (lower decay).
        """
        importance = self._get_importance(path, content)
        access_count, last_access_days = self._get_access_info(path)

        decay_score = 0.0
        reason = ""

        if "episodic" in memory_type.lower():
            half_life = self.config.episodic_half_life_days
            if last_access_days is not None:
                decay_score = 1.0 - (importance * math.pow(0.5, last_access_days / half_life))
                if access_count < self.config.access_count_threshold:
                    decay_score += 0.2
                reason = f"episodic: {last_access_days:.0f}d since access, imp={importance:.2f}"
            else:
                decay_score = 0.5
                reason = "episodic: never accessed"
        else:
            if importance < self.config.semantic_min_importance:
                decay_score = 1.0 - importance
                reason = f"semantic: low importance {importance:.2f}"
            elif (
                access_count < self.config.access_count_threshold
                and last_access_days
                and last_access_days > 60
            ):
                decay_score = 0.4
                reason = "semantic: rarely accessed"

        return DecayCandidate(
            path=path,
            memory_type=memory_type,
            importance=importance,
            last_access_days=last_access_days,
            access_count=access_count,
            decay_score=decay_score,
            reason=reason,
        )

    def get_decay_candidates(self) -> List[DecayCandidate]:
        """Get list of memories that would be archived (dry-run)."""
        candidates = []
        if not self.current_dir.exists():
            return candidates

        for subdir in MEMORY_TYPES:
            dir_path = self.current_dir / subdir
            if not dir_path.exists():
                continue
            for f in dir_path.rglob("*"):
                if not f.is_file() or f.suffix.lower() not in (".md", ".txt"):
                    continue
                try:
                    rel_path = str(f.relative_to(self.current_dir))
                    content = f.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                cand = self.compute_decay_score(rel_path, content, subdir)
                if cand.decay_score > 0.5:
                    candidates.append(cand)

        candidates.sort(key=lambda x: x.decay_score, reverse=True)
        return candidates

    def apply_decay(self, candidates: Optional[List[DecayCandidate]] = None) -> int:
        """
        Archive low-importance memories to .mem/forgetting/.

        Returns count of files archived.
        """
        if candidates is None:
            candidates = self.get_decay_candidates()
        self.forgetting_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        archive_sub = self.forgetting_dir / ts
        archive_sub.mkdir(exist_ok=True)
        count = 0
        for cand in candidates:
            if cand.decay_score <= 0.5:
                continue
            src = self.current_dir / cand.path
            if not src.exists():
                continue
            try:
                safe_name = cand.path.replace("/", "_").replace("..", "_")
                dest = (archive_sub / safe_name).resolve()
                dest.relative_to(self.forgetting_dir.resolve())
                shutil.move(str(src), str(dest))
                count += 1
            except (ValueError, Exception):
                continue
        return count
