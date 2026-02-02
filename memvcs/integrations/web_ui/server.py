"""
agmem Web UI server - FastAPI app for browsing history and diffs.
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Will be set when app is created
_repo_path: Optional[Path] = None


def create_app(repo_path: Path) -> FastAPI:
    """Create FastAPI app for the given repository."""
    global _repo_path
    _repo_path = Path(repo_path).resolve()

    app = FastAPI(title="agmem", description="Agent Memory Version Control")

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html = (static_dir / "index.html").read_text()
        return HTMLResponse(html)

    @app.get("/api/log")
    async def api_log(max_count: int = 50):
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")
        commits = repo.get_log(max_count=max_count)
        return {"commits": commits}

    @app.get("/api/tree/{commit_hash}")
    async def api_tree(commit_hash: str):
        from memvcs.core.repository import Repository
        from memvcs.core.objects import Tree, Commit
        from memvcs.core.refs import _valid_commit_hash

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        resolved = repo.resolve_ref(commit_hash) or (
            commit_hash if _valid_commit_hash(commit_hash) else None
        )
        if not resolved:
            raise HTTPException(status_code=400, detail="Invalid revision or hash")
        c = Commit.load(repo.object_store, resolved)
        if not c:
            raise HTTPException(status_code=404, detail="Commit not found")

        tree = Tree.load(repo.object_store, c.tree)
        if not tree:
            return {"entries": []}

        entries = []
        for e in tree.entries:
            path = f"{e.path}/{e.name}" if e.path else e.name
            entries.append({"path": path, "name": e.name, "hash": e.hash, "type": e.obj_type})
        return {"entries": entries}

    @app.get("/api/diff")
    async def api_diff(base: str, head: str):
        from memvcs.core.repository import Repository
        from memvcs.core.diff import DiffEngine

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        c1 = repo.resolve_ref(base)
        c2 = repo.resolve_ref(head)
        if not c1:
            raise HTTPException(status_code=404, detail=f"Unknown revision: {base}")
        if not c2:
            raise HTTPException(status_code=404, detail=f"Unknown revision: {head}")

        engine = DiffEngine(repo.object_store)
        tree_diff = engine.diff_commits(c1, c2)
        files = []
        for fd in tree_diff.files:
            files.append(
                {
                    "path": fd.path,
                    "diff_type": fd.diff_type.value,
                    "old_hash": fd.old_hash,
                    "new_hash": fd.new_hash,
                    "diff_lines": fd.diff_lines,
                }
            )
        return {
            "base": base,
            "head": head,
            "added": tree_diff.added_count,
            "deleted": tree_diff.deleted_count,
            "modified": tree_diff.modified_count,
            "files": files,
        }

    @app.get("/api/blob/{hash_id}")
    async def api_blob(hash_id: str):
        from memvcs.core.repository import Repository
        from memvcs.core.objects import Blob, _valid_object_hash

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")
        if not _valid_object_hash(hash_id):
            raise HTTPException(status_code=400, detail="Invalid object hash")

        blob = Blob.load(repo.object_store, hash_id)
        if not blob:
            raise HTTPException(status_code=404, detail="Blob not found")
        try:
            content = blob.content.decode("utf-8", errors="replace")
        except Exception:
            content = "<binary>"
        return {"hash": hash_id, "content": content}

    @app.get("/api/graph")
    async def api_graph(include_similarity: bool = False, threshold: float = 0.7):
        """Get knowledge graph data for visualization."""
        from memvcs.core.repository import Repository
        from memvcs.core.knowledge_graph import KnowledgeGraphBuilder

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        # Try to get vector store for similarity
        vector_store = None
        if include_similarity:
            try:
                from memvcs.core.vector_store import VectorStore

                vector_store = VectorStore(_repo_path / ".mem")
            except ImportError:
                pass

        builder = KnowledgeGraphBuilder(repo, vector_store)
        graph_data = builder.build_graph(
            include_similarity=include_similarity, similarity_threshold=threshold
        )

        # Return D3-compatible format
        return {
            "nodes": [
                {
                    "id": n.id,
                    "name": n.label,
                    "group": n.memory_type,
                    "size": min(20, max(5, n.size // 100)),
                }
                for n in graph_data.nodes
            ],
            "links": [
                {"source": e.source, "target": e.target, "type": e.edge_type, "value": e.weight}
                for e in graph_data.edges
            ],
            "metadata": graph_data.metadata,
        }

    @app.get("/graph", response_class=HTMLResponse)
    async def graph_view():
        """Serve the knowledge graph visualization page."""
        graph_html = static_dir / "graph.html"
        if graph_html.exists():
            return HTMLResponse(graph_html.read_text())
        else:
            # Return embedded graph viewer
            return HTMLResponse(GRAPH_HTML_TEMPLATE)

    # --- Additional API Endpoints ---

    @app.get("/api/commit/{commit_hash}")
    async def api_commit(commit_hash: str):
        """Get detailed information about a single commit."""
        from memvcs.core.repository import Repository
        from memvcs.core.objects import Commit, Tree
        from memvcs.core.refs import _valid_commit_hash

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        resolved = repo.resolve_ref(commit_hash) or (
            commit_hash if _valid_commit_hash(commit_hash) else None
        )
        if not resolved:
            raise HTTPException(status_code=400, detail="Invalid revision or hash")

        commit = Commit.load(repo.object_store, resolved)
        if not commit:
            raise HTTPException(status_code=404, detail="Commit not found")

        # Get commit data via to_dict()
        commit_data = commit.to_dict()

        # Get file list from tree
        tree = Tree.load(repo.object_store, commit_data["tree"])
        files = []
        if tree:
            for e in tree.entries:
                path = f"{e.path}/{e.name}" if e.path else e.name
                files.append({"path": path, "hash": e.hash, "type": e.obj_type})

        return {
            "hash": resolved,
            "short_hash": resolved[:8],
            "tree": commit_data["tree"],
            "parents": commit_data.get("parents", []),
            "message": commit_data["message"],
            "author": commit_data["author"],
            "timestamp": commit_data["timestamp"],
            "metadata": commit_data.get("metadata", {}),
            "files": files,
        }

    @app.get("/api/trust")
    async def api_trust():
        """Get trust graph data for visualization."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        try:
            from memvcs.core.trust import TrustManager

            trust_mgr = TrustManager(repo.mem_dir)
            agents = trust_mgr.list_agents()

            nodes = []
            links = []

            for agent in agents:
                info = trust_mgr.get_agent_info(agent)
                nodes.append(
                    {
                        "id": agent,
                        "name": info.get("name", agent[:8]),
                        "trust_level": info.get("trust_level", "unknown"),
                        "public_key": info.get("public_key", "")[:16] + "...",
                    }
                )

            # Build trust relationships
            for agent in agents:
                trusted = trust_mgr.get_trusted_agents(agent)
                for trusted_agent in trusted:
                    links.append(
                        {
                            "source": agent,
                            "target": trusted_agent,
                            "trust_level": trust_mgr.get_trust_level(agent, trusted_agent),
                        }
                    )

            return {"nodes": nodes, "links": links}
        except ImportError:
            return {"nodes": [], "links": [], "error": "Trust module not available"}
        except Exception as e:
            return {"nodes": [], "links": [], "error": str(e)}

    @app.get("/api/privacy")
    async def api_privacy():
        """Get privacy budget status."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        try:
            from memvcs.core.privacy_budget import PrivacyBudget

            budget = PrivacyBudget(repo.mem_dir)
            status = budget.get_status()

            return {
                "epsilon_used": status.get("epsilon_used", 0),
                "epsilon_limit": status.get("epsilon_limit", 10),
                "delta_used": status.get("delta_used", 0),
                "delta_limit": status.get("delta_limit", 1e-5),
                "operations_count": status.get("operations_count", 0),
                "percentage_used": min(
                    100, (status.get("epsilon_used", 0) / status.get("epsilon_limit", 10)) * 100
                ),
            }
        except ImportError:
            return {"epsilon_used": 0, "epsilon_limit": 10, "error": "Privacy module not available"}
        except Exception as e:
            return {"epsilon_used": 0, "epsilon_limit": 10, "error": str(e)}

    @app.get("/api/search")
    async def api_search(q: str, memory_type: Optional[str] = None, max_results: int = 20):
        """Search memory files."""
        from memvcs.core.repository import Repository
        from memvcs.core.constants import MEMORY_TYPES

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        if not q or len(q) < 2:
            raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

        query_lower = q.lower()
        results = []

        subdirs = list(MEMORY_TYPES)
        if memory_type and memory_type.lower() in MEMORY_TYPES:
            subdirs = [memory_type.lower()]

        for subdir in subdirs:
            dir_path = repo.current_dir / subdir
            if not dir_path.exists():
                continue

            for f in dir_path.rglob("*"):
                if f.is_file() and len(results) < max_results:
                    try:
                        content = f.read_text(encoding="utf-8", errors="replace")
                        if query_lower in content.lower():
                            rel = str(f.relative_to(repo.current_dir))
                            # Extract matching snippet
                            idx = content.lower().find(query_lower)
                            start = max(0, idx - 50)
                            end = min(len(content), idx + len(q) + 50)
                            snippet = content[start:end]

                            results.append(
                                {
                                    "path": rel,
                                    "memory_type": subdir,
                                    "snippet": snippet,
                                    "filename": f.name,
                                }
                            )
                    except Exception:
                        pass

        return {"query": q, "results": results, "count": len(results)}

    @app.get("/api/status")
    async def api_status():
        """Get repository status."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        status = repo.get_status()
        head = repo.refs.get_head()
        branch = repo.refs.get_current_branch()

        return {
            "branch": branch or "detached",
            "head": head.get("value", "")[:8] if head else None,
            "staged": status.get("staged", []),
            "modified": status.get("modified", []),
            "untracked": status.get("untracked", []),
            "is_clean": not status.get("staged") and not status.get("modified"),
        }

    @app.get("/api/audit")
    async def api_audit(max_entries: int = 50):
        """Get audit log entries."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        try:
            from memvcs.core.audit import read_audit, verify_audit

            entries = read_audit(repo.mem_dir, max_entries=max_entries)
            valid, first_bad = verify_audit(repo.mem_dir)

            return {
                "entries": entries,
                "count": len(entries),
                "valid": valid,
                "first_bad_index": first_bad,
            }
        except ImportError:
            return {"entries": [], "error": "Audit module not available"}
        except Exception as e:
            return {"entries": [], "error": str(e)}

    # --- Collaboration API ---

    @app.get("/api/collaboration")
    async def api_collaboration():
        """Get collaboration dashboard data."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        try:
            from memvcs.core.collaboration import get_collaboration_dashboard

            return get_collaboration_dashboard(repo.mem_dir)
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/agents")
    async def api_agents():
        """Get all registered agents."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        try:
            from memvcs.core.collaboration import AgentRegistry

            registry = AgentRegistry(repo.mem_dir)
            return {"agents": [a.to_dict() for a in registry.list_agents()]}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/trust")
    async def api_trust():
        """Get trust network graph."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        try:
            from memvcs.core.collaboration import TrustManager

            trust_mgr = TrustManager(repo.mem_dir)
            return trust_mgr.get_trust_graph()
        except Exception as e:
            return {"error": str(e), "nodes": [], "links": []}

    # --- Compliance API ---

    @app.get("/api/compliance")
    async def api_compliance():
        """Get compliance dashboard data."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        try:
            from memvcs.core.compliance import get_compliance_dashboard

            return get_compliance_dashboard(repo.mem_dir, repo.current_dir)
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/privacy")
    async def api_privacy():
        """Get privacy budget status."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        try:
            from memvcs.core.compliance import PrivacyManager

            mgr = PrivacyManager(repo.mem_dir)
            return mgr.get_dashboard_data()
        except Exception as e:
            return {"error": str(e), "budgets": []}

    @app.get("/api/integrity")
    async def api_integrity():
        """Get integrity verification status."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        try:
            from memvcs.core.compliance import TamperDetector

            detector = TamperDetector(repo.mem_dir)
            return detector.verify_integrity(repo.current_dir)
        except Exception as e:
            return {"error": str(e), "verified": False}

    # --- Archaeology API ---

    @app.get("/api/archaeology")
    async def api_archaeology():
        """Get archaeology dashboard data."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        try:
            from memvcs.core.archaeology import get_archaeology_dashboard

            return get_archaeology_dashboard(repo.root)
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/forgotten")
    async def api_forgotten(days: int = 30, limit: int = 20):
        """Get forgotten memories."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        try:
            from memvcs.core.archaeology import ForgottenKnowledgeFinder

            finder = ForgottenKnowledgeFinder(repo.root)
            forgotten = finder.find_forgotten(days_threshold=days, limit=limit)
            return {"forgotten": [f.to_dict() for f in forgotten], "count": len(forgotten)}
        except Exception as e:
            return {"error": str(e), "forgotten": []}

    # --- Confidence API ---

    @app.get("/api/confidence")
    async def api_confidence():
        """Get confidence dashboard data."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        try:
            from memvcs.core.confidence import get_confidence_dashboard

            return get_confidence_dashboard(repo.mem_dir)
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/confidence/{path:path}")
    async def api_confidence_score(path: str):
        """Get confidence score for a specific memory."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        try:
            from memvcs.core.confidence import ConfidenceCalculator
            from datetime import datetime, timezone

            calculator = ConfidenceCalculator(repo.mem_dir)
            full_path = repo.current_dir / path

            created_at = None
            if full_path.exists():
                mtime = full_path.stat().st_mtime
                created_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

            score = calculator.calculate_score(path, created_at=created_at)
            return score.to_dict()
        except Exception as e:
            return {"error": str(e)}

    # --- Session API ---

    @app.get("/api/sessions")
    async def api_sessions():
        """Get current session status."""
        from memvcs.core.repository import Repository

        repo = Repository(_repo_path)
        if not repo.is_valid_repo():
            raise HTTPException(status_code=400, detail="Not an agmem repository")

        try:
            from memvcs.core.session import SessionManager

            manager = SessionManager(repo.root)
            return manager.get_status()
        except Exception as e:
            return {"error": str(e), "active": False}

    return app


# Embedded graph viewer template
GRAPH_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>agmem Knowledge Graph</title>
    <meta charset="utf-8">
    <style>
        body {
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
        }
        #header {
            padding: 10px 20px;
            background: #16213e;
            border-bottom: 1px solid #0f3460;
        }
        h1 { margin: 0; font-size: 20px; }
        #controls {
            padding: 10px 20px;
            background: #16213e;
            display: flex;
            gap: 20px;
            align-items: center;
        }
        label { font-size: 14px; }
        #graph { width: 100%; height: calc(100vh - 100px); }
        .node { cursor: pointer; }
        .node text { font-size: 10px; fill: #fff; }
        .link { stroke-opacity: 0.6; }
        .link.reference { stroke: #e94560; }
        .link.similarity { stroke: #0f3460; }
        .link.same_topic { stroke: #533483; }
        .tooltip {
            position: absolute;
            background: #16213e;
            padding: 10px;
            border-radius: 4px;
            border: 1px solid #0f3460;
            font-size: 12px;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.2s;
        }
        #stats { font-size: 12px; color: #888; }
    </style>
</head>
<body>
    <div id="header">
        <h1>agmem Knowledge Graph</h1>
    </div>
    <div id="controls">
        <label><input type="checkbox" id="showLabels" checked> Show labels</label>
        <span id="stats">Loading...</span>
    </div>
    <div id="graph"></div>
    <div id="tooltip" class="tooltip"></div>

    <script src="https://d3js.org/d3.v7.min.js"></script>
    <script>
        const width = window.innerWidth;
        const height = window.innerHeight - 100;
        
        const colorScale = d3.scaleOrdinal()
            .domain(['episodic', 'semantic', 'procedural', 'checkpoints', 'session-summaries', 'unknown'])
            .range(['#e94560', '#0f3460', '#533483', '#1a1a2e', '#16213e', '#444']);
        
        const svg = d3.select('#graph')
            .append('svg')
            .attr('width', width)
            .attr('height', height);
        
        const g = svg.append('g');
        
        // Zoom behavior
        svg.call(d3.zoom()
            .extent([[0, 0], [width, height]])
            .scaleExtent([0.1, 4])
            .on('zoom', ({transform}) => g.attr('transform', transform)));
        
        const tooltip = d3.select('#tooltip');
        
        // Fetch and render graph
        fetch('/api/graph')
            .then(res => res.json())
            .then(data => {
                document.getElementById('stats').textContent = 
                    `${data.nodes.length} files, ${data.links.length} connections`;
                
                const simulation = d3.forceSimulation(data.nodes)
                    .force('link', d3.forceLink(data.links).id(d => d.id).distance(100))
                    .force('charge', d3.forceManyBody().strength(-200))
                    .force('center', d3.forceCenter(width / 2, height / 2));
                
                const link = g.append('g')
                    .selectAll('line')
                    .data(data.links)
                    .join('line')
                    .attr('class', d => `link ${d.type}`)
                    .attr('stroke-width', d => Math.sqrt(d.value) * 2);
                
                const node = g.append('g')
                    .selectAll('g')
                    .data(data.nodes)
                    .join('g')
                    .attr('class', 'node')
                    .call(d3.drag()
                        .on('start', dragstarted)
                        .on('drag', dragged)
                        .on('end', dragended));
                
                node.append('circle')
                    .attr('r', d => d.size)
                    .attr('fill', d => colorScale(d.group))
                    .on('mouseover', (event, d) => {
                        tooltip.style('opacity', 1)
                            .html(`<strong>${d.name}</strong><br>Type: ${d.group}<br>Path: ${d.id}`)
                            .style('left', (event.pageX + 10) + 'px')
                            .style('top', (event.pageY - 10) + 'px');
                    })
                    .on('mouseout', () => tooltip.style('opacity', 0));
                
                const labels = node.append('text')
                    .text(d => d.name)
                    .attr('dx', d => d.size + 3)
                    .attr('dy', 3);
                
                document.getElementById('showLabels').addEventListener('change', (e) => {
                    labels.style('display', e.target.checked ? 'block' : 'none');
                });
                
                simulation.on('tick', () => {
                    link
                        .attr('x1', d => d.source.x)
                        .attr('y1', d => d.source.y)
                        .attr('x2', d => d.target.x)
                        .attr('y2', d => d.target.y);
                    
                    node.attr('transform', d => `translate(${d.x},${d.y})`);
                });
                
                function dragstarted(event) {
                    if (!event.active) simulation.alphaTarget(0.3).restart();
                    event.subject.fx = event.subject.x;
                    event.subject.fy = event.subject.y;
                }
                
                function dragged(event) {
                    event.subject.fx = event.x;
                    event.subject.fy = event.y;
                }
                
                function dragended(event) {
                    if (!event.active) simulation.alphaTarget(0);
                    event.subject.fx = null;
                    event.subject.fy = null;
                }
            })
            .catch(err => {
                document.getElementById('stats').textContent = 'Error loading graph: ' + err;
            });
    </script>
</body>
</html>
"""
