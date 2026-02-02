"""
Federated memory collaboration for agmem.

Agents share model updates or aggregated summaries instead of raw episodic logs.
Optional coordinator URL; optional differential privacy (Tier 3).
"""

import hashlib
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from .config_loader import load_agmem_config
from .protocol_builder import ClientSummaryBuilder


def get_federated_config(repo_root: Path) -> Optional[Dict[str, Any]]:
    """Get federated config from repo/user config. Returns None if disabled."""
    config = load_agmem_config(repo_root)
    fed = config.get("federated") or {}
    if not fed.get("enabled"):
        return None
    url = fed.get("coordinator_url")
    if not url:
        return None
    out = {
        "coordinator_url": url.rstrip("/"),
        "memory_types": fed.get("memory_types", ["episodic", "semantic"]),
    }
    dp = fed.get("differential_privacy") or config.get("differential_privacy") or {}
    if dp.get("enabled"):
        out["use_dp"] = True
        out["dp_epsilon"] = float(dp.get("epsilon", 0.1))
        out["dp_delta"] = float(dp.get("delta", 1e-5))
    else:
        out["use_dp"] = False
    return out


def _normalize_for_hash(text: str) -> str:
    """Normalize text for hashing (no raw content sent)."""
    return " ".join(text.strip().split())


def _extract_topic_from_md(path: Path, content: str) -> str:
    """Extract topic from frontmatter tags or first heading."""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            try:
                import yaml

                fm = yaml.safe_load(content[3:end])
                if isinstance(fm, dict):
                    tags = fm.get("tags", [])
                    if tags:
                        return str(tags[0])[:50]
            except (ImportError, Exception):
                pass
    first_line = content.strip().split("\n")[0] if content.strip() else ""
    if first_line.startswith("#"):
        return first_line.lstrip("#").strip()[:50] or "untitled"
    return "untitled"


def produce_local_summary(
    repo_root: Path,
    memory_types: List[str],
    use_dp: bool = False,
    dp_epsilon: float = 0.1,
    dp_delta: float = 1e-5,
) -> Dict[str, Any]:
    """
    Produce a local summary from episodic/semantic data (no raw content).
    Returns dict with topic counts and fact hashes suitable for coordinator.
    """
    current_dir = repo_root / "current"
    summary = {"memory_types": memory_types, "topics": {}, "topic_hashes": {}, "fact_count": 0}
    all_fact_hashes: List[str] = []

    for mtype in memory_types:
        d = current_dir / mtype
        if not d.exists():
            summary["topics"][mtype] = 0
            summary["topic_hashes"][mtype] = []
            continue
        topic_to_count: Dict[str, int] = {}
        topic_to_hashes: Dict[str, List[str]] = {}
        for f in d.rglob("*.md"):
            if not f.is_file():
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            normalized = _normalize_for_hash(content)
            if normalized:
                h = hashlib.sha256(normalized.encode()).hexdigest()
                all_fact_hashes.append(h)
                topic = _extract_topic_from_md(f, content)
                topic_to_count[topic] = topic_to_count.get(topic, 0) + 1
                topic_to_hashes.setdefault(topic, []).append(h)
        summary["topics"][mtype] = sum(topic_to_count.values())
        summary["topic_hashes"][mtype] = list(topic_to_hashes.keys())
        if mtype == "semantic":
            summary["fact_count"] = len(all_fact_hashes)

    if use_dp and dp_epsilon and dp_delta:
        from .privacy_budget import add_noise

        for mtype in summary["topics"]:
            raw = summary["topics"][mtype]
            summary["topics"][mtype] = max(
                0, int(round(add_noise(float(raw), 1.0, dp_epsilon, dp_delta)))
            )
        summary["fact_count"] = max(
            0, int(round(add_noise(float(summary["fact_count"]), 1.0, dp_epsilon, dp_delta)))
        )

    return summary


def push_updates(repo_root: Path, summary: Dict[str, Any]) -> str:
    """Send local summary to coordinator using protocol-compliant schema.

    Uses ClientSummaryBuilder to ensure the summary conforms to the
    server's PushRequest schema before transmission.

    Returns status message."""
    cfg = get_federated_config(repo_root)
    if not cfg:
        return "Federated collaboration not configured"
    url = cfg["coordinator_url"] + "/push"
    try:
        from .protocol_builder import ClientSummaryBuilder

        # Build protocol-compliant summary
        compliant_summary = ClientSummaryBuilder.build(repo_root, summary, strict_mode=False)

        import urllib.request

        req = urllib.request.Request(
            url,
            data=json.dumps(compliant_summary).encode(),
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
