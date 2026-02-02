"""
agmem MCP Server - Model Context Protocol integration.

Exposes agent memory to Cursor, Claude, and other MCP clients via tools and resources.
Run with: agmem mcp  or  python -m memvcs.integrations.mcp_server

Configure in Cursor/Claude:
  mcpServers.agmem.command = "agmem"
  mcpServers.agmem.args = ["mcp"]
"""

import logging
import os
from pathlib import Path
from typing import Optional

from memvcs.core.constants import MEMORY_TYPES

# Use logging to stderr - never print() in MCP stdio servers
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s: %(message)s",
    stream=__import__("sys").stderr,
)
logger = logging.getLogger("agmem-mcp")


def _capture_observation(tool_name: str, arguments: dict, result: str) -> None:
    """Capture tool call as observation if daemon is running."""
    try:
        from memvcs.core.daemon import capture_observation

        capture_observation(tool_name, arguments, result)
    except ImportError:
        pass  # Daemon module not available
    except Exception as e:
        logger.debug(f"Observation capture failed: {e}")


def _get_repo():
    """Get repository from cwd. Returns (repo, None) or (None, error_msg)."""
    from memvcs.core.repository import Repository

    repo_path = Path(os.getcwd()).resolve()
    repo = Repository(repo_path)
    if not repo.is_valid_repo():
        return None, "Not an agmem repository. Run 'agmem init' first."
    return repo, None


def _create_mcp_server():
    """Create and configure the MCP server. Lazy import to allow running without mcp deps."""
    try:
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP(
            "agmem",
            instructions="Agentic Memory Version Control System - Git for AI agent memories. "
            "Provides tools to read, search, add, and diff agent memory stored in current/.",
        )
    except ImportError:
        try:
            from mcp.server.mcpserver import MCPServer

            mcp = MCPServer("agmem")
        except ImportError:
            try:
                from fastmcp import FastMCP

                mcp = FastMCP("agmem")
            except ImportError:
                raise ImportError(
                    "MCP support requires 'mcp' or 'fastmcp' package. "
                    "Install with: pip install agmem[mcp]"
                )

    # --- Tools ---

    @mcp.tool()
    def memory_read(path: str) -> str:
        """Read a memory file from current/ directory.

        Args:
            path: Relative path within current/ (e.g. semantic/user-preferences.md,
                  episodic/session1.md, procedural/coding-workflow.md)
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        full_path = (repo.current_dir / path).resolve()
        try:
            full_path.relative_to(repo.current_dir.resolve())
        except ValueError:
            return f"Error: Path outside current/: {path}"
        if not full_path.exists():
            return f"Error: File not found: {path}"
        if full_path.is_dir():
            return f"Error: {path} is a directory, not a file"

        try:
            return full_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading {path}: {e}"

    @mcp.tool()
    def memory_search(query: str, memory_type: Optional[str] = None) -> str:
        """Full-text search over memory files in current/.

        Args:
            query: Search term to find in memory content
            memory_type: Optional filter - episodic, semantic, or procedural
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        query_lower = query.lower()
        results = []

        subdirs = list(MEMORY_TYPES)
        if memory_type:
            memory_type = memory_type.lower()
            if memory_type in MEMORY_TYPES:
                subdirs = [memory_type]
            else:
                return "Error: memory_type must be one of: episodic, semantic, procedural"

        for subdir in subdirs:
            dir_path = repo.current_dir / subdir
            if not dir_path.exists():
                continue
            for f in dir_path.rglob("*"):
                if f.is_file():
                    try:
                        content = f.read_text(encoding="utf-8", errors="replace")
                        if query_lower in content.lower():
                            rel = str(f.relative_to(repo.current_dir))
                            results.append(f"--- {rel} ---\n{content[:500]}...")
                    except Exception:
                        pass

        if not results:
            result = f"No matches for '{query}' in memory."
        else:
            result = "\n\n".join(results[:10])
        _capture_observation("memory_search", {"query": query, "memory_type": memory_type}, result)
        return result

    @mcp.tool()
    def memory_add(path: str, commit: bool = False, message: str = "") -> str:
        """Stage a memory file for commit. Optionally commit immediately.

        Args:
            path: Relative path within current/
            commit: If True, commit after staging
            message: Commit message (required if commit=True)
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        full_path = (repo.current_dir / path).resolve()
        try:
            full_path.relative_to(repo.current_dir.resolve())
        except ValueError:
            return f"Error: Path outside current/: {path}"
        if not full_path.exists() or not full_path.is_file():
            return f"Error: File not found: {path}"

        rel_path = str(full_path.relative_to(repo.current_dir))
        try:
            repo.stage_file(rel_path)
        except Exception as e:
            return f"Error staging {path}: {e}"

        if commit:
            if not message:
                return "Staged. Error: message required for commit."
            try:
                commit_hash = repo.commit(message)
                result = f"Staged and committed: {rel_path} ({commit_hash[:8]})"
                _capture_observation("memory_add", {"path": path, "commit": True}, result)
                return result
            except Exception as e:
                return f"Staged. Error committing: {e}"
        result = f"Staged: {rel_path}. Run 'agmem commit -m \"message\"' to save."
        _capture_observation("memory_add", {"path": path, "commit": False}, result)
        return result

    @mcp.tool()
    def memory_log(max_count: int = 10) -> str:
        """Return recent commit history.

        Args:
            max_count: Maximum number of commits to return (default 10)
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        commits = repo.get_log(max_count=max_count)
        if not commits:
            return "No commits yet."

        lines = []
        for c in commits:
            lines.append(f"{c['short_hash']} {c['message']}")
        return "\n".join(lines)

    @mcp.tool()
    def memory_diff(
        base: Optional[str] = None, head: Optional[str] = None, working: bool = False
    ) -> str:
        """Show diff between commits or working tree.

        Args:
            base: Base ref (commit, branch, or tag). Default: HEAD~1
            head: Head ref. Default: HEAD
            working: If True, diff working tree vs HEAD (ignore base/head)
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        from memvcs.core.diff import DiffEngine

        engine = DiffEngine(repo.object_store)

        if working:
            head_commit = repo.get_head_commit()
            if not head_commit:
                return "No commits yet."
            working_files = {}
            for root, dirs, files in os.walk(repo.current_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for f in files:
                    fp = Path(root) / f
                    rel = str(fp.relative_to(repo.current_dir))
                    working_files[rel] = fp.read_bytes()
            tree_diff = engine.diff_working_dir(head_commit.store(repo.object_store), working_files)
            return engine.format_diff(tree_diff, "HEAD", "working")
        else:
            base_ref = base or "HEAD~1"
            head_ref = head or "HEAD"
            c1 = repo.resolve_ref(base_ref)
            c2 = repo.resolve_ref(head_ref)
            if not c1:
                return f"Error: Unknown revision: {base_ref}"
            if not c2:
                return f"Error: Unknown revision: {head_ref}"
            tree_diff = engine.diff_commits(c1, c2)
            return engine.format_diff(tree_diff, base_ref, head_ref)

    # --- Resources: mem://current/{path} (if supported by SDK) ---
    if hasattr(mcp, "resource"):

        @mcp.resource("mem://current/{path}")
        def memory_resource(path: str) -> str:
            """Read memory file from current/ by path. URI: mem://current/semantic/user-preferences.md"""
            repo, err = _get_repo()
            if err:
                return f"Error: {err}"

            full_path = repo.current_dir / path
            if not full_path.exists() or not full_path.is_file():
                return f"File not found: {path}"
            if not str(full_path.resolve()).startswith(str(repo.current_dir.resolve())):
                return f"Path outside current/: {path}"

            return full_path.read_text(encoding="utf-8", errors="replace")

    # --- Progressive Disclosure Search Tools ---

    @mcp.tool()
    def memory_index(query: str, memory_type: Optional[str] = None, limit: int = 20) -> str:
        """Layer 1: Lightweight search returning metadata + first line only.

        Use this first to find relevant memories with minimal token cost.
        Follow up with memory_details for full content of specific files.

        Args:
            query: Search query
            memory_type: Filter by type (episodic, semantic, procedural)
            limit: Maximum results (default 20)
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.search_index import SearchIndex, layer1_cost

            index = SearchIndex(repo.mem_dir)
            # Ensure index is up to date
            index.index_directory(repo.current_dir)

            results = index.search_index(query, memory_type=memory_type, limit=limit)
            index.close()

            if not results:
                return f"No results for: {query}"

            lines = [f"Found {len(results)} results (est. ~{layer1_cost(results)} tokens):"]
            for r in results:
                lines.append(f"- [{r.memory_type}] {r.filename}: {r.first_line[:80]}...")
                lines.append(f"  Path: {r.path}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def memory_timeline(days: int = 7, limit: int = 10) -> str:
        """Layer 2: Get timeline of memory activity grouped by date.

        Shows what was captured each day without full content.

        Args:
            days: Number of days to look back (default 7)
            limit: Maximum entries per day (default 10)
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.search_index import SearchIndex
            from datetime import datetime, timedelta, timezone

            index = SearchIndex(repo.mem_dir)
            index.index_directory(repo.current_dir)

            start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
            timeline = index.get_timeline(start_date=start_date, limit=limit)
            index.close()

            if not timeline:
                return "No activity in timeline."

            lines = [f"Memory timeline (last {days} days):"]
            for entry in timeline:
                lines.append(f"\n## {entry.date} ({entry.file_count} files)")
                for f in entry.files[:5]:
                    lines.append(f"  - [{f['memory_type']}] {f['filename']}")
                if len(entry.files) > 5:
                    lines.append(f"  ... and {len(entry.files) - 5} more")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def memory_details(paths: str) -> str:
        """Layer 3: Get full content of specific memory files.

        Use after memory_index to retrieve complete content.
        Higher token cost - use sparingly.

        Args:
            paths: Comma-separated list of file paths from memory_index results
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.search_index import SearchIndex, layer3_cost

            path_list = [p.strip() for p in paths.split(",")]

            index = SearchIndex(repo.mem_dir)
            details = index.get_full_details(path_list)
            index.close()

            if not details:
                return "No files found."

            lines = [f"Retrieved {len(details)} files (est. ~{layer3_cost(details)} tokens):"]
            for d in details:
                lines.append(f"\n---\n## {d['filename']}\n")
                lines.append(d["content"])
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    # --- Session Management Tools ---

    @mcp.tool()
    def session_start(context: Optional[str] = None) -> str:
        """Start a new work session for automatic memory capture.

        Sessions group related observations and create semantic commits.

        Args:
            context: Optional project or task context description
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.session import SessionManager

            manager = SessionManager(repo.root)
            session = manager.start_session(project_context=context)

            return f"Session started: {session.id}\nContext: {context or 'None'}\nStatus: {session.status}"
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def session_status() -> str:
        """Get current session status and statistics."""
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.session import SessionManager

            manager = SessionManager(repo.root)
            status = manager.get_status()

            if not status.get("active"):
                return "No active session. Use session_start to begin."

            lines = [
                f"Session: {status['session_id']}",
                f"Status: {status['status']}",
                f"Started: {status['started_at']}",
                f"Observations: {status['observation_count']}",
                f"Topics: {', '.join(status.get('topics', [])) or 'None'}",
                f"Commits: {status['commit_count']}",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def session_commit(end_session: bool = False) -> str:
        """Commit current session observations to memory.

        Args:
            end_session: If True, also end the session after committing
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.session import SessionManager

            manager = SessionManager(repo.root)

            if not manager.session:
                return "No active session."

            if end_session:
                commit_hash = manager.end_session(commit=True)
                return f"Session ended and committed: {commit_hash or 'no changes'}"
            else:
                commit_hash = manager._commit_session()
                return f"Session committed: {commit_hash or 'no changes'}"
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def session_end(commit: bool = True) -> str:
        """End the current work session.

        Args:
            commit: If True, commit observations before ending
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.session import SessionManager

            manager = SessionManager(repo.root)
            commit_hash = manager.end_session(commit=commit)
            return f"Session ended. Commit: {commit_hash or 'no changes'}"
        except Exception as e:
            return f"Error: {e}"

    # --- Collaboration Tools ---

    @mcp.tool()
    def agent_register(name: str, agent_type: str = "assistant") -> str:
        """Register a new agent in the collaboration registry.

        Args:
            name: Agent name (e.g., "Claude", "GPT-4")
            agent_type: Type of agent ("assistant", "human", "system")
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.collaboration import AgentRegistry

            registry = AgentRegistry(repo.mem_dir)
            agent = registry.register_agent(name, metadata={"type": agent_type})
            return f"Agent registered: {agent.agent_id} ({agent.name})"
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def trust_grant(from_agent: str, to_agent: str, level: str = "partial") -> str:
        """Grant trust from one agent to another.

        Args:
            from_agent: Agent ID granting trust
            to_agent: Agent ID receiving trust
            level: Trust level ("full", "partial", "read-only", "none")
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.collaboration import TrustManager

            trust_mgr = TrustManager(repo.mem_dir)
            relation = trust_mgr.grant_trust(from_agent, to_agent, level)
            return f"Trust granted: {from_agent} -> {to_agent} ({level})"
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def contributions_list(limit: int = 10) -> str:
        """Get contributor leaderboard.

        Args:
            limit: Maximum contributors to show
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.collaboration import ContributionTracker

            tracker = ContributionTracker(repo.mem_dir)
            leaderboard = tracker.get_leaderboard(limit=limit)

            if not leaderboard:
                return "No contributions recorded yet."

            lines = ["Contribution Leaderboard:"]
            for entry in leaderboard:
                lines.append(
                    f"#{entry['rank']} {entry['agent_id'][:8]}: {entry['commits']} commits"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    # --- Compliance Tools ---

    @mcp.tool()
    def privacy_status(budget_name: Optional[str] = None) -> str:
        """Get privacy budget status.

        Args:
            budget_name: Specific budget to check, or None for all
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.compliance import PrivacyManager

            mgr = PrivacyManager(repo.mem_dir)

            if budget_name:
                budget = mgr.get_budget(budget_name)
                if not budget:
                    return f"Budget not found: {budget_name}"
                return f"Budget '{budget_name}': {budget.remaining():.2%} remaining ({budget.queries_made} queries)"
            else:
                data = mgr.get_dashboard_data()
                if not data["budgets"]:
                    return "No privacy budgets configured."
                lines = ["Privacy Budgets:"]
                for b in data["budgets"]:
                    lines.append(f"- {b['name']}: {b['remaining']:.2%} remaining")
                return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def integrity_verify() -> str:
        """Verify memory integrity using Merkle tree."""
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.compliance import TamperDetector

            detector = TamperDetector(repo.mem_dir)
            result = detector.verify_integrity(repo.current_dir)

            if result.get("error"):
                # First time - store baseline
                detector.store_merkle_state(repo.current_dir)
                return "No baseline found. Created new integrity baseline."

            if result["verified"]:
                return "✓ Integrity verified. No tampering detected."
            else:
                lines = ["⚠ Integrity check failed:"]
                if result["modified_files"]:
                    lines.append(f"  Modified: {', '.join(result['modified_files'][:5])}")
                if result["added_files"]:
                    lines.append(f"  Added: {', '.join(result['added_files'][:5])}")
                if result["deleted_files"]:
                    lines.append(f"  Deleted: {', '.join(result['deleted_files'][:5])}")
                return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    # --- Archaeology Tools ---

    @mcp.tool()
    def forgotten_memories(days: int = 30, limit: int = 10) -> str:
        """Find memories that haven't been accessed recently.

        Args:
            days: Threshold for "forgotten" (default 30 days)
            limit: Maximum results
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.archaeology import ForgottenKnowledgeFinder

            finder = ForgottenKnowledgeFinder(repo.root)
            forgotten = finder.find_forgotten(days_threshold=days, limit=limit)

            if not forgotten:
                return f"No memories older than {days} days found."

            lines = [f"Forgotten memories (>{days} days):"]
            for m in forgotten:
                lines.append(f"- {m.path} ({m.days_since_access}d ago)")
                lines.append(f"  Preview: {m.content_preview[:60]}...")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def find_context(path: str, date: str, window_days: int = 7) -> str:
        """Find what was happening around a memory at a point in time.

        Args:
            path: Memory file path
            date: Target date (YYYY-MM-DD format)
            window_days: Days before/after to search
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.archaeology import ContextReconstructor

            reconstructor = ContextReconstructor(repo.root)
            context = reconstructor.reconstruct_context(path, date, window_days)

            if context.get("error"):
                return f"Error: {context['error']}"

            return f"Context for {path} around {date}:\n{context['summary']}"
        except Exception as e:
            return f"Error: {e}"

    # --- Confidence Tools ---

    @mcp.tool()
    def confidence_score(path: str, source_id: Optional[str] = None) -> str:
        """Get or calculate confidence score for a memory.

        Args:
            path: Memory file path
            source_id: Optional source agent ID
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.confidence import ConfidenceCalculator

            calculator = ConfidenceCalculator(repo.mem_dir)

            # Check file exists
            full_path = repo.current_dir / path
            created_at = None
            if full_path.exists():
                from datetime import datetime, timezone

                mtime = full_path.stat().st_mtime
                created_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

            score = calculator.calculate_score(path, source_id=source_id, created_at=created_at)

            lines = [
                f"Confidence for {path}: {score.score:.1%}",
                f"  Source reliability: {score.factors.source_reliability:.1%}",
                f"  Age: {score.factors.age_days:.1f} days",
                f"  Corroborations: {score.factors.corroboration_count}",
                f"  Contradictions: {score.factors.contradiction_count}",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def low_confidence(threshold: float = 0.5, limit: int = 10) -> str:
        """Find memories with low confidence scores.

        Args:
            threshold: Confidence threshold (0.0-1.0)
            limit: Maximum results
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.confidence import ConfidenceCalculator

            calculator = ConfidenceCalculator(repo.mem_dir)
            low = calculator.get_low_confidence_memories(threshold=threshold)

            if not low:
                return f"No memories below {threshold:.0%} confidence."

            lines = [f"Low confidence memories (<{threshold:.0%}):"]
            for m in low[:limit]:
                lines.append(f"- {m['path']}: {m['score']:.1%}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def expiring_soon(days: int = 7, threshold: float = 0.5) -> str:
        """Find memories that will drop below confidence threshold soon.

        Args:
            days: Days to look ahead
            threshold: Confidence threshold
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.confidence import ConfidenceCalculator

            calculator = ConfidenceCalculator(repo.mem_dir)
            expiring = calculator.get_expiring_soon(days=days, threshold=threshold)

            if not expiring:
                return f"No memories expiring in the next {days} days."

            lines = [f"Expiring within {days} days:"]
            for m in expiring:
                lines.append(
                    f"- {m['path']}: {m['current_score']:.1%} -> <{threshold:.0%} in {m['days_until_threshold']:.1f}d"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    # --- Time Travel Tools ---

    @mcp.tool()
    def time_travel(time_expr: str) -> str:
        """Find memory state at a specific time.

        Args:
            time_expr: Time expression like "2 days ago", "yesterday", "2024-01-15"
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.timetravel import TemporalNavigator

            navigator = TemporalNavigator(repo.root)
            commit = navigator.find_commit_at(time_expr)

            if not commit:
                return f"No commits found at or before: {time_expr}"

            return f"At {time_expr}:\nCommit: {commit['short_hash']}\nMessage: {commit['message']}\nTime: {commit.get('timestamp', 'unknown')}"
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def timeline(days: int = 30) -> str:
        """Get activity timeline.

        Args:
            days: Number of days to include
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.timetravel import TimelineVisualizer

            visualizer = TimelineVisualizer(repo.root)
            timeline_data = visualizer.get_activity_timeline(days=days)

            if not timeline_data:
                return f"No activity in the last {days} days."

            lines = [f"Activity (last {days} days):"]
            for day in timeline_data[-10:]:
                lines.append(f"  {day['period']}: {day['count']} commits")

            total = sum(d["count"] for d in timeline_data)
            lines.append(f"\nTotal: {total} commits")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    # --- Semantic Graph Tools ---

    @mcp.tool()
    def memory_graph(limit: int = 20) -> str:
        """Get semantic memory graph summary.

        Args:
            limit: Maximum nodes to include
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.semantic_graph import get_semantic_graph_dashboard

            dashboard = get_semantic_graph_dashboard(repo.root)

            lines = [
                f"Memory Graph: {dashboard['node_count']} nodes, {dashboard['edge_count']} edges",
                "",
                "By Type:",
            ]
            for t, count in dashboard.get("clusters_by_type", {}).items():
                lines.append(f"  {t}: {count}")

            top_tags = list(dashboard.get("clusters_by_tag", {}).items())[:5]
            if top_tags:
                lines.append("\nTop Tags:")
                for tag, count in top_tags:
                    lines.append(f"  #{tag}: {count} memories")

            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def graph_related(path: str, depth: int = 2) -> str:
        """Find related memories using graph traversal.

        Args:
            path: Memory file path
            depth: Maximum traversal depth
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.semantic_graph import SemanticGraphBuilder, GraphSearchEngine

            builder = SemanticGraphBuilder(repo.root)
            nodes, edges = builder.build_graph()

            # Find node by path
            node_id = None
            for n in nodes:
                if n.path == path or path in n.path:
                    node_id = n.node_id
                    break

            if not node_id:
                return f"Memory not found: {path}"

            nodes_dict = {n.node_id: n for n in nodes}
            engine = GraphSearchEngine(nodes_dict, edges)
            related = engine.find_related(node_id, max_depth=depth, limit=10)

            if not related:
                return "No related memories found."

            lines = [f"Related to {path}:"]
            for node, score, dist in related:
                lines.append(f"  {node.path} (score: {score:.2f}, depth: {dist})")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    # --- Agent Tools ---

    @mcp.tool()
    def agent_health() -> str:
        """Run memory health check."""
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.agents import MemoryAgentManager

            manager = MemoryAgentManager(repo.root)
            health = manager.run_health_check()

            lines = ["Memory Health Check:"]

            cons = health["checks"]["consolidation"]
            lines.append(f"  Consolidation candidates: {cons['candidate_count']}")

            clean = health["checks"]["cleanup"]
            lines.append(f"  Cleanup candidates: {clean['candidate_count']}")

            dups = health["checks"]["duplicates"]
            lines.append(f"  Duplicate groups: {dups['duplicate_groups']}")

            alerts = health.get("alerts", [])
            lines.append(f"  Active alerts: {len(alerts)}")

            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def find_duplicates() -> str:
        """Find duplicate memory files."""
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.agents import CleanupAgent

            agent = CleanupAgent(repo.root)
            duplicates = agent.find_duplicates()

            if not duplicates:
                return "No duplicate memories found."

            lines = [f"Found {len(duplicates)} duplicate groups:"]
            for dup in duplicates[:10]:
                lines.append(f"\nGroup ({dup['count']} files):")
                for f in dup["files"][:3]:
                    lines.append(f"  - {f}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def consolidation_candidates() -> str:
        """Find memories that could be consolidated."""
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.agents import ConsolidationAgent

            agent = ConsolidationAgent(repo.root)
            candidates = agent.find_consolidation_candidates()

            if not candidates:
                return "No consolidation candidates found."

            lines = ["Consolidation candidates:"]
            for c in candidates[:10]:
                lines.append(f"\n{c['prefix']}: {c['file_count']} files")
                lines.append(f"  {c['suggestion']}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def cleanup_candidates(max_age_days: int = 90) -> str:
        """Find old memories that could be cleaned up.

        Args:
            max_age_days: Minimum age in days
        """
        repo, err = _get_repo()
        if err:
            return f"Error: {err}"

        try:
            from memvcs.core.agents import CleanupAgent

            agent = CleanupAgent(repo.root)
            candidates = agent.find_cleanup_candidates(max_age_days=max_age_days)

            if not candidates:
                return f"No memories older than {max_age_days} days."

            lines = [f"Old memories (>{max_age_days} days):"]
            for c in candidates[:10]:
                lines.append(f"  {c['path']} ({c['age_days']}d old)")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    return mcp


def run():
    """Run the MCP server. Uses stdio transport for Cursor/Claude."""
    mcp = _create_mcp_server()
    # Default: stdio for Cursor/Claude Desktop
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
