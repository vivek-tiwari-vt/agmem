"""
Multi-Agent Collaboration - Trust management and agent registry.

This module provides:
- Agent identity and key management
- Trust relationships between agents
- Contribution tracking and attribution
- Conflict detection and resolution helpers
"""

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class Agent:
    """Represents an agent identity."""

    agent_id: str
    name: str
    public_key: Optional[str] = None
    created_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "public_key": self.public_key,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Agent":
        return cls(
            agent_id=data["agent_id"],
            name=data["name"],
            public_key=data.get("public_key"),
            created_at=data.get("created_at"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class TrustRelation:
    """A trust relationship between two agents."""

    from_agent: str
    to_agent: str
    trust_level: str  # "full", "partial", "read-only", "none"
    created_at: str
    reason: Optional[str] = None
    expires_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "trust_level": self.trust_level,
            "created_at": self.created_at,
            "reason": self.reason,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrustRelation":
        return cls(
            from_agent=data["from_agent"],
            to_agent=data["to_agent"],
            trust_level=data["trust_level"],
            created_at=data["created_at"],
            reason=data.get("reason"),
            expires_at=data.get("expires_at"),
        )


@dataclass
class Contribution:
    """A contribution by an agent to memory."""

    agent_id: str
    commit_hash: str
    timestamp: str
    files_changed: int
    additions: int
    deletions: int
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "commit_hash": self.commit_hash,
            "timestamp": self.timestamp,
            "files_changed": self.files_changed,
            "additions": self.additions,
            "deletions": self.deletions,
            "message": self.message,
        }


class AgentRegistry:
    """Registry for managing agent identities."""

    def __init__(self, mem_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.agents_file = self.mem_dir / "agents.json"
        self._agents: Dict[str, Agent] = {}
        self._load()

    def _load(self) -> None:
        """Load agents from disk."""
        if self.agents_file.exists():
            try:
                data = json.loads(self.agents_file.read_text())
                self._agents = {
                    aid: Agent.from_dict(a) for aid, a in data.get("agents", {}).items()
                }
            except Exception:
                self._agents = {}

    def _save(self) -> None:
        """Save agents to disk."""
        self.mem_dir.mkdir(parents=True, exist_ok=True)
        data = {"agents": {aid: a.to_dict() for aid, a in self._agents.items()}}
        self.agents_file.write_text(json.dumps(data, indent=2))

    def register_agent(
        self, name: str, public_key: Optional[str] = None, metadata: Optional[Dict] = None
    ) -> Agent:
        """Register a new agent."""
        agent_id = hashlib.sha256(
            f"{name}{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:16]

        agent = Agent(
            agent_id=agent_id,
            name=name,
            public_key=public_key,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )

        self._agents[agent_id] = agent
        self._save()
        return agent

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> List[Agent]:
        """List all registered agents."""
        return list(self._agents.values())

    def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            self._save()
            return True
        return False


class TrustManager:
    """Manages trust relationships between agents."""

    TRUST_LEVELS = ["full", "partial", "read-only", "none"]

    def __init__(self, mem_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.trust_file = self.mem_dir / "trust.json"
        self._relations: List[TrustRelation] = []
        self._load()

    def _load(self) -> None:
        """Load trust relations from disk."""
        if self.trust_file.exists():
            try:
                data = json.loads(self.trust_file.read_text())
                self._relations = [TrustRelation.from_dict(r) for r in data.get("relations", [])]
            except Exception:
                self._relations = []

    def _save(self) -> None:
        """Save trust relations to disk."""
        self.mem_dir.mkdir(parents=True, exist_ok=True)
        data = {"relations": [r.to_dict() for r in self._relations]}
        self.trust_file.write_text(json.dumps(data, indent=2))

    def grant_trust(
        self,
        from_agent: str,
        to_agent: str,
        trust_level: str,
        reason: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> TrustRelation:
        """Grant trust from one agent to another."""
        if trust_level not in self.TRUST_LEVELS:
            raise ValueError(f"Invalid trust level: {trust_level}")

        # Remove existing relation
        self._relations = [
            r
            for r in self._relations
            if not (r.from_agent == from_agent and r.to_agent == to_agent)
        ]

        relation = TrustRelation(
            from_agent=from_agent,
            to_agent=to_agent,
            trust_level=trust_level,
            created_at=datetime.now(timezone.utc).isoformat(),
            reason=reason,
            expires_at=expires_at,
        )

        self._relations.append(relation)
        self._save()
        return relation

    def revoke_trust(self, from_agent: str, to_agent: str) -> bool:
        """Revoke trust between agents."""
        original_count = len(self._relations)
        self._relations = [
            r
            for r in self._relations
            if not (r.from_agent == from_agent and r.to_agent == to_agent)
        ]
        if len(self._relations) < original_count:
            self._save()
            return True
        return False

    def get_trust_level(self, from_agent: str, to_agent: str) -> str:
        """Get trust level from one agent to another."""
        for r in self._relations:
            if r.from_agent == from_agent and r.to_agent == to_agent:
                return r.trust_level
        return "none"

    def get_trusted_by(self, agent_id: str) -> List[TrustRelation]:
        """Get agents that trust this agent."""
        return [r for r in self._relations if r.to_agent == agent_id]

    def get_trusts(self, agent_id: str) -> List[TrustRelation]:
        """Get agents this agent trusts."""
        return [r for r in self._relations if r.from_agent == agent_id]

    def get_trust_graph(self) -> Dict[str, Any]:
        """Get trust graph data for visualization."""
        agents: Set[str] = set()
        for r in self._relations:
            agents.add(r.from_agent)
            agents.add(r.to_agent)

        nodes = [{"id": a, "name": a[:8]} for a in agents]
        links = [
            {
                "source": r.from_agent,
                "target": r.to_agent,
                "trust_level": r.trust_level,
                "value": {"full": 3, "partial": 2, "read-only": 1, "none": 0}.get(r.trust_level, 0),
            }
            for r in self._relations
        ]

        return {"nodes": nodes, "links": links}


class ContributionTracker:
    """Tracks contributions by agents to memory."""

    def __init__(self, mem_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.contributions_file = self.mem_dir / "contributions.json"
        self._contributions: List[Contribution] = []
        self._load()

    def _load(self) -> None:
        """Load contributions from disk."""
        if self.contributions_file.exists():
            try:
                data = json.loads(self.contributions_file.read_text())
                self._contributions = [Contribution(**c) for c in data.get("contributions", [])]
            except Exception:
                self._contributions = []

    def _save(self) -> None:
        """Save contributions to disk."""
        self.mem_dir.mkdir(parents=True, exist_ok=True)
        data = {"contributions": [c.to_dict() for c in self._contributions]}
        self.contributions_file.write_text(json.dumps(data, indent=2))

    def record_contribution(
        self,
        agent_id: str,
        commit_hash: str,
        files_changed: int,
        additions: int,
        deletions: int,
        message: Optional[str] = None,
    ) -> Contribution:
        """Record a contribution by an agent."""
        contribution = Contribution(
            agent_id=agent_id,
            commit_hash=commit_hash,
            timestamp=datetime.now(timezone.utc).isoformat(),
            files_changed=files_changed,
            additions=additions,
            deletions=deletions,
            message=message,
        )

        self._contributions.append(contribution)
        self._save()
        return contribution

    def get_contributions(self, agent_id: str) -> List[Contribution]:
        """Get all contributions by an agent."""
        return [c for c in self._contributions if c.agent_id == agent_id]

    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get leaderboard of top contributors."""
        stats: Dict[str, Dict[str, int]] = {}

        for c in self._contributions:
            if c.agent_id not in stats:
                stats[c.agent_id] = {"commits": 0, "additions": 0, "deletions": 0}
            stats[c.agent_id]["commits"] += 1
            stats[c.agent_id]["additions"] += c.additions
            stats[c.agent_id]["deletions"] += c.deletions

        sorted_agents = sorted(
            stats.items(),
            key=lambda x: x[1]["commits"],
            reverse=True,
        )

        return [
            {"agent_id": aid, "rank": i + 1, **s}
            for i, (aid, s) in enumerate(sorted_agents[:limit])
        ]

    def get_timeline(self, limit: int = 20) -> List[Contribution]:
        """Get recent contributions timeline."""
        sorted_contributions = sorted(
            self._contributions,
            key=lambda c: c.timestamp,
            reverse=True,
        )
        return sorted_contributions[:limit]


class ConflictDetector:
    """Detects and helps resolve conflicts between agents."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def detect_conflicts(self, base_commit: str, head_commits: List[str]) -> List[Dict[str, Any]]:
        """Detect conflicts between commits from different agents."""
        conflicts = []

        try:
            from memvcs.core.repository import Repository
            from memvcs.core.diff import DiffEngine

            repo = Repository(self.repo_root)
            engine = DiffEngine(repo.object_store)

            # Get files changed in each head commit
            head_files: Dict[str, Set[str]] = {}
            for head in head_commits:
                diff = engine.diff_commits(base_commit, head)
                head_files[head] = set(f.path for f in diff.files)

            # Find overlapping files
            all_heads = list(head_files.keys())
            for i, head1 in enumerate(all_heads):
                for head2 in all_heads[i + 1 :]:
                    overlapping = head_files[head1] & head_files[head2]
                    for path in overlapping:
                        conflicts.append(
                            {
                                "path": path,
                                "commits": [head1, head2],
                                "type": "concurrent_modification",
                            }
                        )

        except Exception:
            pass

        return conflicts

    def suggest_resolution(self, conflict: Dict[str, Any]) -> Dict[str, Any]:
        """Suggest a resolution for a conflict."""
        suggestions = {
            "concurrent_modification": [
                "Use the most recent version",
                "Merge changes manually",
                "Ask the agents to resolve",
            ],
        }

        conflict_type = conflict.get("type", "unknown")
        return {
            "conflict": conflict,
            "suggestions": suggestions.get(conflict_type, ["Manual review required"]),
        }


# --- Web UI Helpers ---


def get_collaboration_dashboard(mem_dir: Path) -> Dict[str, Any]:
    """Get data for the collaboration dashboard."""
    registry = AgentRegistry(mem_dir)
    trust_mgr = TrustManager(mem_dir)
    contrib_tracker = ContributionTracker(mem_dir)

    return {
        "agents": [a.to_dict() for a in registry.list_agents()],
        "trust_graph": trust_mgr.get_trust_graph(),
        "leaderboard": contrib_tracker.get_leaderboard(),
        "recent_activity": [c.to_dict() for c in contrib_tracker.get_timeline(10)],
    }
