"""
Differential privacy budget tracking for agmem.

Per-repo epsilon spent; block when budget exceeded.
"""

import json
import math
from pathlib import Path
from typing import Optional, Tuple


def _budget_path(mem_dir: Path) -> Path:
    return mem_dir / "privacy_budget.json"


def load_budget(mem_dir: Path) -> Tuple[float, float, float]:
    """Load (epsilon_spent, max_epsilon, delta). Returns (0, max, delta) if no file."""
    path = _budget_path(mem_dir)
    if not path.exists():
        config = mem_dir / "config.json"
        max_eps = 1.0
        delta = 1e-5
        if config.exists():
            try:
                c = json.loads(config.read_text())
                dp = c.get("differential_privacy", {})
                max_eps = float(dp.get("max_epsilon", 1.0))
                delta = float(dp.get("delta", 1e-5))
            except Exception:
                pass
        return (0.0, max_eps, delta)
    try:
        data = json.loads(path.read_text())
        return (
            float(data.get("epsilon_spent", 0)),
            float(data.get("max_epsilon", 1.0)),
            float(data.get("delta", 1e-5)),
        )
    except Exception:
        return (0.0, 1.0, 1e-5)


def spend_epsilon(mem_dir: Path, epsilon: float, max_epsilon: Optional[float] = None) -> bool:
    """Record epsilon spent. Returns False if budget would be exceeded."""
    spent, max_eps, delta = load_budget(mem_dir)
    if max_epsilon is not None:
        max_eps = max_epsilon
    if spent + epsilon > max_eps:
        return False
    mem_dir.mkdir(parents=True, exist_ok=True)
    path = _budget_path(mem_dir)
    data = {"epsilon_spent": spent + epsilon, "max_epsilon": max_eps, "delta": delta}
    path.write_text(json.dumps(data, indent=2))
    return True


def add_noise(value: float, sensitivity: float, epsilon: float, delta: float = 1e-5) -> float:
    """Add Gaussian noise for (epsilon, delta)-DP. sigma = sensitivity * sqrt(2*ln(1.25/delta)) / epsilon."""
    import random

    sigma = sensitivity * math.sqrt(2 * math.log(1.25 / delta)) / epsilon
    return value + random.gauss(0, sigma)
