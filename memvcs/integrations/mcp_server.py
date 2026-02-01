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
            return f"No matches for '{query}' in memory."
        return "\n\n".join(results[:10])

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
                return f"Staged and committed: {rel_path} ({commit_hash[:8]})"
            except Exception as e:
                return f"Staged. Error committing: {e}"
        return f"Staged: {rel_path}. Run 'agmem commit -m \"message\"' to save."

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

    return mcp


def run():
    """Run the MCP server. Uses stdio transport for Cursor/Claude."""
    mcp = _create_mcp_server()
    # Default: stdio for Cursor/Claude Desktop
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
