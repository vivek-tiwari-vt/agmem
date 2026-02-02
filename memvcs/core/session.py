"""
Session-Aware Auto-Commit - Smart session management with contextual commits.

This module provides intelligent session tracking and auto-commit functionality:
- Session lifecycle management (start, end, pause, resume)
- Topic-based observation grouping
- Time-window batching
- Semantic commit message generation
- Crash recovery with disk-backed buffers
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib


@dataclass
class SessionConfig:
    """Configuration for session behavior."""

    # Time-based triggers
    idle_timeout_seconds: int = 300  # End session after 5 min idle
    max_session_hours: float = 8.0  # Force commit after 8 hours
    min_session_seconds: int = 60  # Don't commit tiny sessions

    # Batching settings
    commit_interval_seconds: int = 300  # Batch commits every 5 min
    max_observations_per_commit: int = 50
    min_observations_for_commit: int = 3

    # Topic grouping
    enable_topic_grouping: bool = True
    topic_similarity_threshold: float = 0.7

    # Message generation
    use_llm_messages: bool = True


@dataclass
class Observation:
    """A single observation in a session."""

    id: str
    timestamp: str
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[str] = None
    topic: Optional[str] = None
    memory_type: str = "episodic"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result": self.result,
            "topic": self.topic,
            "memory_type": self.memory_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Observation":
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            tool_name=data["tool_name"],
            arguments=data.get("arguments", {}),
            result=data.get("result"),
            topic=data.get("topic"),
            memory_type=data.get("memory_type", "episodic"),
        )


@dataclass
class Session:
    """A work session with observations and metadata."""

    id: str
    started_at: str
    project_context: Optional[str] = None
    observations: List[Observation] = field(default_factory=list)
    topics: Dict[str, List[str]] = field(default_factory=dict)  # topic -> observation_ids
    last_activity: Optional[str] = None
    ended_at: Optional[str] = None
    commit_count: int = 0
    status: str = "active"  # active, paused, ended

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "started_at": self.started_at,
            "project_context": self.project_context,
            "observations": [o.to_dict() for o in self.observations],
            "topics": self.topics,
            "last_activity": self.last_activity,
            "ended_at": self.ended_at,
            "commit_count": self.commit_count,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        return cls(
            id=data["id"],
            started_at=data["started_at"],
            project_context=data.get("project_context"),
            observations=[Observation.from_dict(o) for o in data.get("observations", [])],
            topics=data.get("topics", {}),
            last_activity=data.get("last_activity"),
            ended_at=data.get("ended_at"),
            commit_count=data.get("commit_count", 0),
            status=data.get("status", "active"),
        )


class TopicClassifier:
    """Classifies observations into topics based on tool names and arguments."""

    # Topic keywords for classification
    TOPIC_PATTERNS = {
        "file_operations": ["write_file", "read_file", "delete_file", "move_file", "copy_file"],
        "git_operations": ["git_commit", "git_push", "git_pull", "git_branch", "git_merge"],
        "database": ["query", "insert", "update", "delete", "migrate", "sql"],
        "testing": ["test", "pytest", "unittest", "assertion", "mock"],
        "deployment": ["deploy", "build", "docker", "kubernetes", "ci_cd", "pipeline"],
        "research": ["search", "fetch", "web", "api", "http", "request"],
        "code_generation": ["generate", "create", "scaffold", "template"],
        "refactoring": ["refactor", "rename", "extract", "inline", "move"],
        "debugging": ["debug", "fix", "error", "exception", "trace"],
        "documentation": ["doc", "readme", "comment", "markdown"],
    }

    def classify(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Classify an observation into a topic."""
        tool_lower = tool_name.lower()

        # Check tool name patterns
        for topic, patterns in self.TOPIC_PATTERNS.items():
            for pattern in patterns:
                if pattern in tool_lower:
                    return topic

        # Check argument values for hints
        arg_str = json.dumps(arguments).lower()
        for topic, patterns in self.TOPIC_PATTERNS.items():
            for pattern in patterns:
                if pattern in arg_str:
                    return topic

        return "general"


class SessionManager:
    """Manages session lifecycle, observation batching, and auto-commits."""

    def __init__(self, repo_root: Path, config: Optional[SessionConfig] = None):
        self.repo_root = Path(repo_root)
        self.mem_dir = self.repo_root / ".mem"
        self.session_file = self.mem_dir / "current_session.json"
        self.config = config or SessionConfig()
        self.topic_classifier = TopicClassifier()
        self._session: Optional[Session] = None

    @property
    def session(self) -> Optional[Session]:
        """Get current session, loading from disk if needed."""
        if self._session is None:
            self._session = self._load_session()
        return self._session

    def _now(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    # --- Session Lifecycle ---

    def start_session(self, project_context: Optional[str] = None) -> Session:
        """Start a new session or resume existing one."""
        existing = self._load_session()
        if existing and existing.status == "active":
            # Resume existing session
            self._session = existing
            return existing

        # Create new session
        session = Session(
            id=str(uuid.uuid4())[:8],
            started_at=self._now(),
            project_context=project_context,
            last_activity=self._now(),
        )
        self._session = session
        self._save_session()
        return session

    def end_session(self, commit: bool = True) -> Optional[str]:
        """End current session, optionally committing observations."""
        if not self.session:
            return None

        self.session.ended_at = self._now()
        self.session.status = "ended"

        commit_hash = None
        if commit and self.session.observations:
            commit_hash = self._commit_session()

        self._save_session()
        return commit_hash

    def pause_session(self) -> None:
        """Pause current session (for breaks)."""
        if self.session:
            self.session.status = "paused"
            self._save_session()

    def resume_session(self) -> Optional[Session]:
        """Resume a paused session."""
        session = self._load_session()
        if session and session.status == "paused":
            session.status = "active"
            session.last_activity = self._now()
            self._session = session
            self._save_session()
            return session
        return None

    def discard_session(self) -> None:
        """Discard current session without committing."""
        if self.session_file.exists():
            self.session_file.unlink()
        self._session = None

    # --- Observation Handling ---

    def add_observation(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Optional[str] = None,
    ) -> Optional[str]:
        """Add an observation to the current session. Returns observation ID."""
        session = self.session
        if not session or session.status != "active":
            # Auto-start session if none active
            session = self.start_session()

        # Create observation
        obs_id = hashlib.sha256(
            f"{self._now()}{tool_name}{json.dumps(arguments)}".encode()
        ).hexdigest()[:12]

        topic = self.topic_classifier.classify(tool_name, arguments)
        memory_type = self._infer_memory_type(tool_name)

        observation = Observation(
            id=obs_id,
            timestamp=self._now(),
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            topic=topic,
            memory_type=memory_type,
        )

        session.observations.append(observation)
        session.last_activity = self._now()

        # Track topic grouping
        if topic not in session.topics:
            session.topics[topic] = []
        session.topics[topic].append(obs_id)

        self._save_session()

        # Check if we should auto-commit
        if self._should_commit():
            self._commit_batch()

        return obs_id

    def _infer_memory_type(self, tool_name: str) -> str:
        """Infer memory type from tool name."""
        tool_lower = tool_name.lower()

        episodic_keywords = ["write", "delete", "run", "execute", "commit", "deploy"]
        semantic_keywords = ["search", "read", "fetch", "query", "get"]
        procedural_keywords = ["generate", "create", "refactor", "template"]

        for kw in episodic_keywords:
            if kw in tool_lower:
                return "episodic"
        for kw in semantic_keywords:
            if kw in tool_lower:
                return "semantic"
        for kw in procedural_keywords:
            if kw in tool_lower:
                return "procedural"

        return "episodic"

    def _should_commit(self) -> bool:
        """Check if we should trigger an auto-commit."""
        if not self.session:
            return False

        obs_count = len(self.session.observations)

        # Buffer full
        if obs_count >= self.config.max_observations_per_commit:
            return True

        # Check time since last commit or session start
        if obs_count >= self.config.min_observations_for_commit:
            last_time = self.session.last_activity or self.session.started_at
            try:
                last_dt = datetime.fromisoformat(last_time.replace("Z", "+00:00"))
                elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                if elapsed >= self.config.commit_interval_seconds:
                    return True
            except Exception:
                pass

        return False

    # --- Commit Logic ---

    def _commit_batch(self) -> Optional[str]:
        """Commit current batch of observations."""
        if not self.session or not self.session.observations:
            return None

        return self._commit_session()

    def _commit_session(self) -> Optional[str]:
        """Commit session observations to repository."""
        if not self.session or not self.session.observations:
            return None

        try:
            from memvcs.core.repository import Repository

            repo = Repository(self.repo_root)
            if not repo.is_valid_repo():
                return None

            # Write observations as session summary
            session_content = self._generate_session_content()
            session_path = (
                repo.current_dir / "episodic" / "sessions" / f"session-{self.session.id}.md"
            )
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session_path.write_text(session_content)

            # Stage and commit
            repo.stage_file(str(session_path.relative_to(repo.current_dir)))
            message = self._generate_commit_message()
            commit_hash = repo.commit(message)

            # Update session
            self.session.commit_count += 1
            self.session.observations.clear()
            self.session.topics.clear()
            self._save_session()

            return commit_hash
        except Exception:
            return None

    def _generate_session_content(self) -> str:
        """Generate markdown content for session summary."""
        session = self.session
        if not session:
            return ""

        lines = [
            "---",
            f'session_id: "{session.id}"',
            f'started_at: "{session.started_at}"',
            f"observation_count: {len(session.observations)}",
            f"topics: [{', '.join(session.topics.keys())}]",
            "---",
            "",
            f"# Session {session.id}",
            "",
        ]

        if session.project_context:
            lines.append(f"**Context:** {session.project_context}")
            lines.append("")

        # Group by topic
        if session.topics:
            lines.append("## Activity by Topic")
            lines.append("")
            for topic, obs_ids in session.topics.items():
                lines.append(f"### {topic.replace('_', ' ').title()}")
                topic_obs = [o for o in session.observations if o.id in obs_ids]
                for obs in topic_obs[:5]:  # Limit per topic
                    ts = obs.timestamp.split("T")[1][:8] if "T" in obs.timestamp else ""
                    lines.append(f"- [{ts}] `{obs.tool_name}`")
                if len(topic_obs) > 5:
                    lines.append(f"- ... and {len(topic_obs) - 5} more")
                lines.append("")

        lines.append("## Timeline")
        lines.append("")
        for obs in session.observations[-10:]:  # Last 10
            ts = obs.timestamp.split("T")[1][:8] if "T" in obs.timestamp else ""
            args_str = ", ".join(f"{k}={v}" for k, v in list(obs.arguments.items())[:2])
            lines.append(f"- [{ts}] `{obs.tool_name}`: {args_str[:80]}")

        return "\n".join(lines)

    def _generate_commit_message(self) -> str:
        """Generate commit message for session."""
        session = self.session
        if not session:
            return "Session commit"

        obs_count = len(session.observations)
        topics = list(session.topics.keys())

        if self.config.use_llm_messages:
            # Could call LLM here for better messages
            pass

        # Template-based message
        if len(topics) == 1:
            return f"Session: {obs_count} observations ({topics[0]})"
        elif len(topics) <= 3:
            topics_str = ", ".join(topics)
            return f"Session: {obs_count} observations ({topics_str})"
        else:
            return f"Session: {obs_count} observations across {len(topics)} topics"

    # --- Persistence ---

    def _save_session(self) -> None:
        """Save current session to disk."""
        if not self._session:
            return

        self.mem_dir.mkdir(parents=True, exist_ok=True)
        with open(self.session_file, "w") as f:
            json.dump(self._session.to_dict(), f, indent=2)

    def _load_session(self) -> Optional[Session]:
        """Load session from disk."""
        if not self.session_file.exists():
            return None

        try:
            with open(self.session_file) as f:
                data = json.load(f)
            return Session.from_dict(data)
        except Exception:
            return None

    def get_status(self) -> Dict[str, Any]:
        """Get current session status."""
        session = self.session
        if not session:
            return {"active": False}

        return {
            "active": session.status == "active",
            "session_id": session.id,
            "status": session.status,
            "started_at": session.started_at,
            "observation_count": len(session.observations),
            "topics": list(session.topics.keys()),
            "commit_count": session.commit_count,
            "last_activity": session.last_activity,
        }


# --- CLI Helper Functions ---


def session_start(repo_root: Path, context: Optional[str] = None) -> Dict[str, Any]:
    """Start a new session."""
    manager = SessionManager(repo_root)
    session = manager.start_session(context)
    return manager.get_status()


def session_end(repo_root: Path, commit: bool = True) -> Dict[str, Any]:
    """End the current session."""
    manager = SessionManager(repo_root)
    commit_hash = manager.end_session(commit=commit)
    return {"ended": True, "commit_hash": commit_hash}


def session_status(repo_root: Path) -> Dict[str, Any]:
    """Get session status."""
    manager = SessionManager(repo_root)
    return manager.get_status()


def session_commit(repo_root: Path) -> Dict[str, Any]:
    """Force commit current observations."""
    manager = SessionManager(repo_root)
    if manager.session and manager.session.observations:
        commit_hash = manager._commit_session()
        return {"committed": True, "commit_hash": commit_hash}
    return {"committed": False, "reason": "No observations to commit"}


def session_discard(repo_root: Path) -> Dict[str, Any]:
    """Discard current session."""
    manager = SessionManager(repo_root)
    manager.discard_session()
    return {"discarded": True}
