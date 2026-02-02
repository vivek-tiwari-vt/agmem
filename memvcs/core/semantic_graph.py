"""
Semantic Memory Graph - Knowledge graph with relationships and embeddings.

This module provides:
- Memory node graph building
- Relationship inference
- Semantic clustering
- Graph-based search
"""

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class MemoryNode:
    """A node in the semantic memory graph."""

    node_id: str
    path: str
    memory_type: str
    title: str
    content_hash: str
    created_at: str
    tags: List[str] = field(default_factory=list)
    embedding: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "path": self.path,
            "memory_type": self.memory_type,
            "title": self.title,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
            "tags": self.tags,
        }


@dataclass
class MemoryEdge:
    """An edge between memory nodes."""

    source_id: str
    target_id: str
    relationship: str  # "references", "similar", "precedes", "related"
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "relationship": self.relationship,
            "weight": self.weight,
        }


class SemanticGraphBuilder:
    """Builds a semantic graph from memory files."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.nodes: Dict[str, MemoryNode] = {}
        self.edges: List[MemoryEdge] = []

    def build_graph(self) -> Tuple[List[MemoryNode], List[MemoryEdge]]:
        """Build the complete semantic graph."""
        from memvcs.core.repository import Repository

        try:
            repo = Repository(self.repo_root)
            current_dir = repo.current_dir

            # Build nodes
            for filepath in current_dir.rglob("*"):
                if filepath.is_file():
                    node = self._create_node(filepath, current_dir)
                    if node:
                        self.nodes[node.node_id] = node

            # Build edges
            self._infer_reference_edges()
            self._infer_similarity_edges()
            self._infer_temporal_edges()

            return list(self.nodes.values()), self.edges
        except Exception:
            return [], []

    def _create_node(self, filepath: Path, base_dir: Path) -> Optional[MemoryNode]:
        """Create a node from a file."""
        try:
            rel_path = str(filepath.relative_to(base_dir))
            content = filepath.read_text(encoding="utf-8", errors="replace")

            # Determine memory type
            memory_type = "unknown"
            for mt in ["episodic", "semantic", "procedural"]:
                if mt in filepath.parts:
                    memory_type = mt
                    break

            # Extract title
            title = filepath.stem
            for line in content.split("\n")[:5]:
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

            # Extract tags from YAML frontmatter or content
            tags = self._extract_tags(content)

            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            mtime = datetime.fromtimestamp(filepath.stat().st_mtime, tz=timezone.utc).isoformat()

            return MemoryNode(
                node_id=content_hash,
                path=rel_path,
                memory_type=memory_type,
                title=title,
                content_hash=content_hash,
                created_at=mtime,
                tags=tags,
            )
        except Exception:
            return None

    def _extract_tags(self, content: str) -> List[str]:
        """Extract tags from content."""
        import re

        tags = set()

        # Look for YAML frontmatter tags
        if content.startswith("---"):
            match = re.search(r"tags:\s*\[([^\]]+)\]", content[:1000])
            if match:
                tags.update(t.strip().strip("'\"") for t in match.group(1).split(","))

        # Look for hashtags
        hashtags = re.findall(r"#(\w+)", content)
        tags.update(hashtags[:10])  # Limit hashtags

        return list(tags)[:20]

    def _infer_reference_edges(self) -> None:
        """Find explicit references between memories."""
        import re

        for node in self.nodes.values():
            try:
                filepath = self.repo_root / ".mem" / "current" / node.path
                if not filepath.exists():
                    filepath = self.repo_root / node.path
                if not filepath.exists():
                    continue

                content = filepath.read_text(encoding="utf-8", errors="replace")

                # Find markdown links
                links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
                for _, target in links:
                    if not target.startswith("http"):
                        # Internal link
                        target_path = target.lstrip("./")
                        for other_node in self.nodes.values():
                            if (
                                other_node.path.endswith(target_path)
                                or target_path in other_node.path
                            ):
                                self.edges.append(
                                    MemoryEdge(
                                        source_id=node.node_id,
                                        target_id=other_node.node_id,
                                        relationship="references",
                                        weight=1.0,
                                    )
                                )
                                break
            except Exception:
                pass

    def _infer_similarity_edges(self) -> None:
        """Find similar memories based on tags."""
        nodes_list = list(self.nodes.values())

        for i, node1 in enumerate(nodes_list):
            for node2 in nodes_list[i + 1 :]:
                if node1.tags and node2.tags:
                    common_tags = set(node1.tags) & set(node2.tags)
                    if common_tags:
                        weight = len(common_tags) / max(len(node1.tags), len(node2.tags))
                        if weight >= 0.3:  # Threshold
                            self.edges.append(
                                MemoryEdge(
                                    source_id=node1.node_id,
                                    target_id=node2.node_id,
                                    relationship="similar",
                                    weight=weight,
                                    metadata={"common_tags": list(common_tags)},
                                )
                            )

    def _infer_temporal_edges(self) -> None:
        """Find temporal relationships between memories."""
        # Sort by creation time
        sorted_nodes = sorted(self.nodes.values(), key=lambda n: n.created_at)

        # Connect sequential memories of the same type
        by_type: Dict[str, List[MemoryNode]] = defaultdict(list)
        for node in sorted_nodes:
            by_type[node.memory_type].append(node)

        for nodes_list in by_type.values():
            for i in range(len(nodes_list) - 1):
                self.edges.append(
                    MemoryEdge(
                        source_id=nodes_list[i].node_id,
                        target_id=nodes_list[i + 1].node_id,
                        relationship="precedes",
                        weight=0.5,
                    )
                )


class SemanticClusterer:
    """Clusters memories based on semantic similarity."""

    def __init__(self, nodes: List[MemoryNode], edges: List[MemoryEdge]):
        self.nodes = {n.node_id: n for n in nodes}
        self.edges = edges

    def cluster_by_tags(self, min_cluster_size: int = 2) -> Dict[str, List[str]]:
        """Cluster nodes by shared tags."""
        # Build tag -> nodes mapping
        tag_to_nodes: Dict[str, Set[str]] = defaultdict(set)
        for node in self.nodes.values():
            for tag in node.tags:
                tag_to_nodes[tag].add(node.node_id)

        # Filter to meaningful clusters
        clusters = {}
        for tag, node_ids in tag_to_nodes.items():
            if len(node_ids) >= min_cluster_size:
                clusters[tag] = list(node_ids)

        return clusters

    def cluster_by_type(self) -> Dict[str, List[str]]:
        """Cluster nodes by memory type."""
        clusters: Dict[str, List[str]] = defaultdict(list)
        for node in self.nodes.values():
            clusters[node.memory_type].append(node.node_id)
        return dict(clusters)

    def find_communities(self, min_connections: int = 2) -> List[Set[str]]:
        """Find communities using simple connected components."""
        # Build adjacency list
        adj: Dict[str, Set[str]] = defaultdict(set)
        for edge in self.edges:
            if edge.weight >= 0.5:  # Only strong connections
                adj[edge.source_id].add(edge.target_id)
                adj[edge.target_id].add(edge.source_id)

        # Find connected components
        visited: Set[str] = set()
        communities: List[Set[str]] = []

        for node_id in self.nodes:
            if node_id not in visited:
                component: Set[str] = set()
                stack = [node_id]
                while stack:
                    current = stack.pop()
                    if current not in visited:
                        visited.add(current)
                        component.add(current)
                        stack.extend(adj[current] - visited)

                if len(component) >= min_connections:
                    communities.append(component)

        return sorted(communities, key=len, reverse=True)


class GraphSearchEngine:
    """Search using graph traversal."""

    def __init__(self, nodes: Dict[str, MemoryNode], edges: List[MemoryEdge]):
        self.nodes = nodes
        self.edges = edges
        self._build_index()

    def _build_index(self) -> None:
        """Build adjacency index."""
        self.outgoing: Dict[str, List[MemoryEdge]] = defaultdict(list)
        self.incoming: Dict[str, List[MemoryEdge]] = defaultdict(list)

        for edge in self.edges:
            self.outgoing[edge.source_id].append(edge)
            self.incoming[edge.target_id].append(edge)

    def find_related(
        self, node_id: str, max_depth: int = 2, limit: int = 10
    ) -> List[Tuple[MemoryNode, float, int]]:
        """Find related nodes using graph traversal."""
        if node_id not in self.nodes:
            return []

        visited: Dict[str, Tuple[float, int]] = {}  # node_id -> (score, depth)
        queue: List[Tuple[str, float, int]] = [(node_id, 1.0, 0)]

        while queue:
            current_id, score, depth = queue.pop(0)

            if current_id in visited:
                continue
            visited[current_id] = (score, depth)

            if depth >= max_depth:
                continue

            # Traverse outgoing edges
            for edge in self.outgoing.get(current_id, []):
                next_score = score * edge.weight * 0.7  # Decay factor
                if edge.target_id not in visited:
                    queue.append((edge.target_id, next_score, depth + 1))

            # Traverse incoming edges
            for edge in self.incoming.get(current_id, []):
                next_score = score * edge.weight * 0.5  # Lower for backlinks
                if edge.source_id not in visited:
                    queue.append((edge.source_id, next_score, depth + 1))

        # Remove starting node and sort by score
        del visited[node_id]
        results = [
            (self.nodes[nid], score, depth)
            for nid, (score, depth) in visited.items()
            if nid in self.nodes
        ]
        results.sort(key=lambda x: x[1], reverse=True)

        return results[:limit]

    def search_by_tags(self, tags: List[str], limit: int = 10) -> List[MemoryNode]:
        """Search for nodes by tags."""
        tag_set = set(t.lower() for t in tags)
        scored_nodes: List[Tuple[MemoryNode, float]] = []

        for node in self.nodes.values():
            node_tags = set(t.lower() for t in node.tags)
            overlap = tag_set & node_tags
            if overlap:
                score = len(overlap) / len(tag_set)
                scored_nodes.append((node, score))

        scored_nodes.sort(key=lambda x: x[1], reverse=True)
        return [n for n, _ in scored_nodes[:limit]]


# --- Dashboard Helper ---


def get_semantic_graph_dashboard(repo_root: Path) -> Dict[str, Any]:
    """Get data for semantic graph dashboard."""
    builder = SemanticGraphBuilder(repo_root)
    nodes, edges = builder.build_graph()

    clusterer = SemanticClusterer(nodes, edges)
    type_clusters = clusterer.cluster_by_type()
    tag_clusters = clusterer.cluster_by_tags()

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": [n.to_dict() for n in nodes[:50]],
        "edges": [e.to_dict() for e in edges[:100]],
        "clusters_by_type": {k: len(v) for k, v in type_clusters.items()},
        "clusters_by_tag": {k: len(v) for k, v in list(tag_clusters.items())[:10]},
    }
