"""
Real-Time Observation Daemon for agmem.

Background process that watches MCP tool activity and automatically commits
observations to the memory repository.

Features:
- MCP event stream listener (file-based or watchdog)
- Observation extraction and memory type classification  
- Auto-staging with type-specific paths
- Batched auto-commit with LLM-generated messages
- Session management with crash recovery
"""

import json
import logging
import os
import signal
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("agmem-daemon")


@dataclass
class Observation:
    """A single observation from an MCP tool call."""

    id: str
    timestamp: str
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[str] = None
    memory_type: str = "episodic"  # episodic, semantic, procedural
    summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result": self.result,
            "memory_type": self.memory_type,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Observation":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            tool_name=data["tool_name"],
            arguments=data.get("arguments", {}),
            result=data.get("result"),
            memory_type=data.get("memory_type", "episodic"),
            summary=data.get("summary"),
        )


@dataclass
class SessionState:
    """State of the current observation session."""

    session_id: str
    started_at: str
    observations: List[Observation] = field(default_factory=list)
    last_commit_at: Optional[str] = None
    commit_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "observations": [o.to_dict() for o in self.observations],
            "last_commit_at": self.last_commit_at,
            "commit_count": self.commit_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        return cls(
            session_id=data["session_id"],
            started_at=data["started_at"],
            observations=[Observation.from_dict(o) for o in data.get("observations", [])],
            last_commit_at=data.get("last_commit_at"),
            commit_count=data.get("commit_count", 0),
        )


class ObservationExtractor:
    """Extracts observations from MCP tool calls and classifies memory types."""

    # Tool name patterns → memory type mapping
    MEMORY_TYPE_MAP = {
        # Episodic: Events, actions, what happened
        "episodic": [
            "run_command",
            "execute",
            "shell",
            "terminal",
            "write_file",
            "create_file",
            "delete_file",
            "move_file",
            "copy_file",
            "mkdir",
            "git_",
            "deploy",
            "build",
            "test",
            "lint",
        ],
        # Semantic: Knowledge, facts, data
        "semantic": [
            "search",
            "read_file",
            "read_url",
            "fetch",
            "get_",
            "list_",
            "query",
            "lookup",
            "find",
            "browse",
            "api_call",
            "database",
            "memory_read",
            "memory_search",
        ],
        # Procedural: How-to, processes, workflows
        "procedural": [
            "generate",
            "refactor",
            "implement",
            "create_",
            "setup",
            "configure",
            "install",
            "workflow",
            "pipeline",
            "template",
        ],
    }

    # Tools to ignore (trivial operations)
    IGNORE_TOOLS = {
        "echo",
        "pwd",
        "whoami",
        "date",
        "clear",
        "history",
        "noop",
        "ping",
    }

    def __init__(self, min_content_length: int = 50):
        self.min_content_length = min_content_length

    def should_capture(self, tool_name: str, result: Optional[str] = None) -> bool:
        """Determine if this tool call should be captured as an observation."""
        if tool_name.lower() in self.IGNORE_TOOLS:
            return False
        if result and len(result) < self.min_content_length:
            return False
        return True

    def classify_memory_type(self, tool_name: str) -> str:
        """Classify the tool call into a memory type."""
        tool_lower = tool_name.lower()
        for memory_type, patterns in self.MEMORY_TYPE_MAP.items():
            for pattern in patterns:
                if pattern in tool_lower:
                    return memory_type
        return "episodic"  # Default to episodic

    def extract(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Optional[str] = None,
    ) -> Optional[Observation]:
        """Extract an observation from a tool call."""
        if not self.should_capture(tool_name, result):
            return None

        memory_type = self.classify_memory_type(tool_name)

        # Generate summary from tool name and key arguments
        summary_parts = [tool_name]
        for key in ["path", "file", "url", "query", "command"]:
            if key in arguments:
                val = str(arguments[key])[:100]
                summary_parts.append(f"{key}={val}")

        return Observation(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool_name=tool_name,
            arguments=arguments,
            result=result[:2000] if result else None,  # Truncate large results
            memory_type=memory_type,
            summary=" ".join(summary_parts)[:200],
        )


class AutoStagingEngine:
    """Writes observations to the current/ directory with type-specific paths."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.current_dir = self.repo_root / "current"

    def stage_observation(self, observation: Observation) -> Path:
        """Write observation to current/ directory and return the path."""
        # Parse timestamp for date/time path components
        ts = datetime.fromisoformat(observation.timestamp.replace("Z", "+00:00"))
        date_str = ts.strftime("%Y-%m-%d")
        time_str = ts.strftime("%H-%M-%S")

        # Build path based on memory type
        if observation.memory_type == "episodic":
            # episodic/YYYY-MM-DD/HH-MM-SS-tool_name.md
            subdir = self.current_dir / "episodic" / date_str
            filename = f"{time_str}-{observation.tool_name}.md"
        elif observation.memory_type == "semantic":
            # semantic/topic_name.md (use tool_name as topic)
            subdir = self.current_dir / "semantic"
            filename = f"{observation.tool_name}-{observation.id[:8]}.md"
        else:
            # procedural/task_name.md
            subdir = self.current_dir / "procedural"
            filename = f"{observation.tool_name}-{observation.id[:8]}.md"

        subdir.mkdir(parents=True, exist_ok=True)
        filepath = subdir / filename

        # Format content as markdown
        content = self._format_observation_md(observation)
        filepath.write_text(content, encoding="utf-8")

        return filepath

    def _format_observation_md(self, observation: Observation) -> str:
        """Format observation as markdown with YAML frontmatter."""
        args_json = json.dumps(observation.arguments, indent=2, default=str)
        result_preview = (observation.result or "")[:500]
        if observation.result and len(observation.result) > 500:
            result_preview += "\n... (truncated)"

        return f"""---
schema_version: "1.0"
memory_type: {observation.memory_type}
observation_id: {observation.id}
timestamp: {observation.timestamp}
tool_name: {observation.tool_name}
auto_captured: true
---

# {observation.summary or observation.tool_name}

## Tool Call

**Tool:** `{observation.tool_name}`
**Time:** {observation.timestamp}

### Arguments

```json
{args_json}
```

### Result

```
{result_preview}
```
"""


class CommitMessageGenerator:
    """Generates semantic commit messages from observations using LLM or templates."""

    def __init__(self, use_llm: bool = True, llm_model: str = "gpt-4o-mini"):
        self.use_llm = use_llm
        self.llm_model = llm_model

    def generate(self, observations: List[Observation]) -> str:
        """Generate a commit message for a batch of observations."""
        if not observations:
            return "Auto-commit: Empty observation batch"

        if self.use_llm:
            try:
                return self._generate_llm(observations)
            except Exception as e:
                logger.warning(f"LLM message generation failed: {e}, falling back to template")

        return self._generate_template(observations)

    def _generate_template(self, observations: List[Observation]) -> str:
        """Generate a template-based commit message."""
        tool_counts: Dict[str, int] = {}
        for obs in observations:
            tool_counts[obs.tool_name] = tool_counts.get(obs.tool_name, 0) + 1

        # Build subject line
        if len(tool_counts) == 1:
            tool_name = list(tool_counts.keys())[0]
            count = tool_counts[tool_name]
            subject = f"Auto-commit: {count} {tool_name} observation(s)"
        else:
            subject = f"Auto-commit: {len(observations)} observations from {len(tool_counts)} tools"

        # Build body
        body_lines = ["", "Captured observations:"]
        for obs in observations[:10]:  # Show first 10
            body_lines.append(f"- [{obs.memory_type}] {obs.summary or obs.tool_name}")
        if len(observations) > 10:
            body_lines.append(f"... and {len(observations) - 10} more")

        return subject + "\n" + "\n".join(body_lines)

    def _generate_llm(self, observations: List[Observation]) -> str:
        """Generate commit message using LLM."""
        try:
            from memvcs.core.llm import get_llm_provider
        except ImportError:
            logger.warning("LLM provider not available, using template")
            return self._generate_template(observations)

        provider = get_llm_provider()
        if not provider:
            return self._generate_template(observations)

        # Build observation summary for prompt
        obs_text = "\n".join(
            f"- {obs.timestamp}: {obs.tool_name} - {obs.summary or 'No summary'}"
            for obs in observations[:20]
        )

        prompt = f"""Generate a concise Git-style commit message for these agent observations:

{obs_text}

Requirements:
- Subject line: max 50 chars, imperative mood (e.g., "Implement", "Fix", "Update")
- Body: bullet points of key changes (optional if simple)
- Focus on WHAT was accomplished, not individual tool calls

Output only the commit message, no explanations."""

        try:
            response = provider.complete(prompt, model=self.llm_model, max_tokens=200)
            return response.strip()
        except Exception as e:
            logger.warning(f"LLM call failed: {e}")
            return self._generate_template(observations)


class ObservationDaemon:
    """Background daemon that captures observations and auto-commits."""

    def __init__(
        self,
        repo_root: Path,
        commit_interval_seconds: int = 300,
        max_buffer_size: int = 50,
        use_llm_messages: bool = True,
    ):
        self.repo_root = Path(repo_root)
        self.mem_dir = self.repo_root / ".mem"
        self.commit_interval = commit_interval_seconds
        self.max_buffer_size = max_buffer_size

        self.extractor = ObservationExtractor()
        self.stager = AutoStagingEngine(repo_root)
        self.message_gen = CommitMessageGenerator(use_llm=use_llm_messages)

        self.session: Optional[SessionState] = None
        self._running = False
        self._commit_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    # --- Session Management ---

    def _session_file(self) -> Path:
        return self.mem_dir / "daemon_session.json"

    def _buffer_file(self) -> Path:
        return self.mem_dir / "daemon_buffer.jsonl"

    def _pid_file(self) -> Path:
        return self.mem_dir / "daemon.pid"

    def _load_session(self) -> Optional[SessionState]:
        """Load existing session from disk if available."""
        path = self._session_file()
        if path.exists():
            try:
                data = json.loads(path.read_text())
                return SessionState.from_dict(data)
            except Exception as e:
                logger.warning(f"Failed to load session: {e}")
        return None

    def _save_session(self) -> None:
        """Persist session state to disk."""
        if not self.session:
            return
        path = self._session_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.session.to_dict(), indent=2))

    def _append_to_buffer(self, observation: Observation) -> None:
        """Append observation to disk buffer for crash recovery."""
        path = self._buffer_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(observation.to_dict()) + "\n")

    def _clear_buffer(self) -> None:
        """Clear the disk buffer after successful commit."""
        path = self._buffer_file()
        if path.exists():
            path.unlink()

    def _recover_buffer(self) -> List[Observation]:
        """Recover observations from disk buffer."""
        path = self._buffer_file()
        if not path.exists():
            return []

        observations = []
        for line in path.read_text().strip().split("\n"):
            if line.strip():
                try:
                    observations.append(Observation.from_dict(json.loads(line)))
                except Exception:
                    pass
        return observations

    # --- Daemon Lifecycle ---

    def start(self) -> None:
        """Start the daemon."""
        if self._running:
            logger.warning("Daemon already running")
            return

        # Check if another daemon is running
        pid_file = self._pid_file()
        if pid_file.exists():
            try:
                old_pid = int(pid_file.read_text().strip())
                # Check if process is still running
                try:
                    os.kill(old_pid, 0)
                    logger.error(f"Another daemon is running (PID: {old_pid})")
                    return
                except OSError:
                    pass  # Process not running, continue
            except Exception:
                pass

        # Write PID file
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))

        # Load or create session
        self.session = self._load_session()
        if not self.session:
            self.session = SessionState(
                session_id=str(uuid.uuid4()),
                started_at=datetime.now(timezone.utc).isoformat(),
            )

        # Recover any buffered observations
        recovered = self._recover_buffer()
        if recovered:
            logger.info(f"Recovered {len(recovered)} observations from buffer")
            self.session.observations.extend(recovered)

        self._running = True
        self._save_session()
        self._start_commit_timer()

        logger.info(
            f"Daemon started (session: {self.session.session_id[:8]}, "
            f"observations: {len(self.session.observations)})"
        )

    def stop(self) -> None:
        """Stop the daemon gracefully."""
        if not self._running:
            return

        logger.info("Stopping daemon...")
        self._running = False

        # Cancel commit timer
        if self._commit_timer:
            self._commit_timer.cancel()

        # Final commit if there are pending observations
        if self.session and self.session.observations:
            self._commit_observations()

        # Clean up
        self._save_session()
        pid_file = self._pid_file()
        if pid_file.exists():
            pid_file.unlink()

        logger.info("Daemon stopped")

    def _start_commit_timer(self) -> None:
        """Start the periodic commit timer."""
        if not self._running:
            return

        self._commit_timer = threading.Timer(
            self.commit_interval,
            self._on_commit_timer,
        )
        self._commit_timer.daemon = True
        self._commit_timer.start()

    def _on_commit_timer(self) -> None:
        """Timer callback for periodic commits."""
        if not self._running:
            return

        with self._lock:
            if self.session and self.session.observations:
                self._commit_observations()

        self._start_commit_timer()

    # --- Observation Handling ---

    def add_observation(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Optional[str] = None,
    ) -> Optional[str]:
        """Add a new observation. Returns observation ID if captured."""
        if not self._running or not self.session:
            logger.warning("Daemon not running, observation not captured")
            return None

        observation = self.extractor.extract(tool_name, arguments, result)
        if not observation:
            return None

        with self._lock:
            # Stage the observation file
            self.stager.stage_observation(observation)

            # Add to session
            self.session.observations.append(observation)
            self._append_to_buffer(observation)
            self._save_session()

            # Auto-commit if buffer is full
            if len(self.session.observations) >= self.max_buffer_size:
                self._commit_observations()

        logger.debug(f"Captured: {observation.tool_name} ({observation.memory_type})")
        return observation.id

    def _commit_observations(self) -> Optional[str]:
        """Commit all pending observations."""
        if not self.session or not self.session.observations:
            return None

        try:
            from memvcs.core.repository import Repository
            from memvcs.core.audit import append_audit
        except ImportError as e:
            logger.error(f"Failed to import repository: {e}")
            return None

        try:
            repo = Repository(self.repo_root)
            if not repo.is_valid_repo():
                logger.error("Not a valid agmem repository")
                return None

            # Stage all observation files
            repo.stage_directory("")

            # Generate commit message
            message = self.message_gen.generate(self.session.observations)

            # Commit with metadata
            commit_hash = repo.commit(
                message,
                metadata={
                    "daemon_session_id": self.session.session_id,
                    "observation_count": len(self.session.observations),
                    "auto_commit": True,
                },
            )

            # Log to audit trail
            append_audit(
                self.mem_dir,
                "daemon_commit",
                {
                    "session_id": self.session.session_id,
                    "commit_hash": commit_hash,
                    "observations_count": len(self.session.observations),
                },
            )

            logger.info(
                f"Committed {len(self.session.observations)} observations: {commit_hash[:8]}"
            )

            # Clear buffer and observations
            self._clear_buffer()
            self.session.observations = []
            self.session.last_commit_at = datetime.now(timezone.utc).isoformat()
            self.session.commit_count += 1
            self._save_session()

            return commit_hash

        except Exception as e:
            logger.error(f"Commit failed: {e}")
            return None

    # --- Status and Info ---

    def get_status(self) -> Dict[str, Any]:
        """Get daemon status information."""
        return {
            "running": self._running,
            "session_id": self.session.session_id if self.session else None,
            "started_at": self.session.started_at if self.session else None,
            "pending_observations": len(self.session.observations) if self.session else 0,
            "commit_count": self.session.commit_count if self.session else 0,
            "last_commit_at": self.session.last_commit_at if self.session else None,
            "commit_interval_seconds": self.commit_interval,
            "max_buffer_size": self.max_buffer_size,
        }


# --- Daemon Process Entry Point ---


def _handle_signals(daemon: ObservationDaemon) -> None:
    """Set up signal handlers for graceful shutdown."""

    def handler(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}, shutting down...")
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def run_daemon(
    repo_root: Path,
    commit_interval: int = 300,
    max_buffer: int = 50,
    use_llm: bool = True,
    foreground: bool = False,
) -> int:
    """Run the observation daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    daemon = ObservationDaemon(
        repo_root=repo_root,
        commit_interval_seconds=commit_interval,
        max_buffer_size=max_buffer,
        use_llm_messages=use_llm,
    )

    _handle_signals(daemon)
    daemon.start()

    if foreground:
        try:
            while daemon._running:
                time.sleep(1)
        except KeyboardInterrupt:
            daemon.stop()

    return 0


# --- Public API for MCP integration ---


_daemon_instance: Optional[ObservationDaemon] = None


def get_daemon() -> Optional[ObservationDaemon]:
    """Get the global daemon instance."""
    return _daemon_instance


def initialize_daemon(repo_root: Path, **kwargs: Any) -> ObservationDaemon:
    """Initialize and return the global daemon instance."""
    global _daemon_instance
    if _daemon_instance is None:
        _daemon_instance = ObservationDaemon(repo_root, **kwargs)
    return _daemon_instance


def capture_observation(
    tool_name: str,
    arguments: Dict[str, Any],
    result: Optional[str] = None,
) -> Optional[str]:
    """Capture an observation via the global daemon. Returns observation ID if captured."""
    daemon = get_daemon()
    if daemon and daemon._running:
        return daemon.add_observation(tool_name, arguments, result)
    return None
