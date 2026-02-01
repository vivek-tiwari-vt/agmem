"""
Federated memory collaboration for agmem.

Agents share model updates or aggregated summaries instead of raw episodic logs.
Optional coordinator URL; optional differential privacy (Tier 3).
"""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from .config_loader import load_agmem_config


def get_federated_config(repo_root: Path) -> Optional[Dict[str, Any]]:
    """Get federated config from repo/user config. Returns None if disabled."""
    config = load_agmem_config(repo_root)
    fed = config.get("federated") or {}
    if not fed.get("enabled"):
        return None
    url = fed.get("coordinator_url")
    if not url:
        return None
    return {
        "coordinator_url": url.rstrip("/"),
        "memory_types": fed.get("memory_types", ["episodic", "semantic"]),
    }


def produce_local_summary(repo_root: Path, memory_types: List[str]) -> Dict[str, Any]:
    """
    Produce a local summary from episodic/semantic data (no raw content).
    Returns dict suitable for sending to coordinator (e.g. topic counts, fact hashes).
    """
    current_dir = repo_root / "current"
    summary = {"memory_types": memory_types, "topics": {}, "fact_count": 0}
    for mtype in memory_types:
        d = current_dir / mtype
        if not d.exists():
            continue
        count = 0
        for f in d.rglob("*.md"):
            if f.is_file():
                count += 1
        summary["topics"][mtype] = count
        if mtype == "semantic":
            summary["fact_count"] = count
    return summary


def push_updates(repo_root: Path, summary: Dict[str, Any]) -> str:
    """Send local summary to coordinator. Returns status message."""
    cfg = get_federated_config(repo_root)
    if not cfg:
        return "Federated collaboration not configured"
    url = cfg["coordinator_url"] + "/push"
    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            data=json.dumps(summary).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status in (200, 201):
                return "Pushed updates to coordinator"
            return f"Coordinator returned {resp.status}"
    except Exception as e:
        return f"Push failed: {e}"


def pull_merged(repo_root: Path) -> Optional[Dict[str, Any]]:
    """Pull merged summaries from coordinator. Returns merged data or None."""
    cfg = get_federated_config(repo_root)
    if not cfg:
        return None
    url = cfg["coordinator_url"] + "/pull"
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None
