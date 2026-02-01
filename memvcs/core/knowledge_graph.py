"""
Knowledge graph builder for agmem.

Visualizes connections between memory files to spot contradictions or knowledge islands.
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict

try:
    import networkx as nx

    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False


@dataclass
class GraphNode:
    """A node in the knowledge graph (represents a memory file)."""

    id: str  # File path
    label: str  # Display name
    memory_type: str  # episodic, semantic, procedural
    size: int  # Content size
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.memory_type,
            "size": self.size,
            "tags": self.tags,
        }


@dataclass
class GraphEdge:
    """An edge in the knowledge graph (represents a connection)."""

    source: str
    target: str
    edge_type: str  # "reference", "similarity", "same_topic"
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.edge_type,
            "weight": self.weight,
        }


@dataclass
class KnowledgeGraphData:
    """Complete graph data for export."""

    nodes: List[GraphNode]
    edges: List[GraphEdge]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class KnowledgeGraphBuilder:
    """
    Builds a knowledge graph from memory files.

    Detects connections through:
    1. Wikilinks: [[filename]] references
    2. Semantic similarity: Using embeddings
    3. Shared tags: Files with common tags
    4. Co-occurrence: Facts in same episodic session (optional)
    """

    # Pattern for wikilinks: [[target]] or [[target|display text]]
    WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

    def __init__(self, repo, vector_store=None):
        """
        Initialize the graph builder.

        Args:
            repo: Repository instance
            vector_store: Optional VectorStore for semantic similarity
        """
        self.repo = repo
        self.vector_store = vector_store
        self.current_dir = repo.root / "current"

        self._graph = None
        if NETWORKX_AVAILABLE:
            self._graph = nx.DiGraph()

    def _detect_memory_type(self, filepath: str) -> str:
        """Detect memory type from file path."""
        path_lower = filepath.lower()
        if "episodic" in path_lower:
            return "episodic"
        elif "semantic" in path_lower:
            return "semantic"
        elif "procedural" in path_lower:
            return "procedural"
        elif "checkpoint" in path_lower:
            return "checkpoints"
        elif "session-summar" in path_lower:
            return "session-summaries"
        return "unknown"

    def _extract_wikilinks(self, content: str) -> Set[str]:
        """Extract wikilink targets from content."""
        matches = self.WIKILINK_PATTERN.findall(content)
        return set(matches)

    def _extract_tags_from_frontmatter(self, content: str) -> List[str]:
        """Extract tags from YAML frontmatter."""
        try:
            import yaml
            from .schema import FrontmatterParser

            fm, _ = FrontmatterParser.parse(content)
            if fm and fm.tags:
                return fm.tags
        except Exception:
            pass
        return []

    def _normalize_link_target(self, target: str, source_path: str) -> Optional[str]:
        """
        Normalize a wikilink target to a file path.

        Args:
            target: Wikilink target (e.g., "user-preferences")
            source_path: Path of the source file

        Returns:
            Normalized file path or None if not found
        """
        # Try exact match
        for ext in [".md", ".txt", ""]:
            check_path = self.current_dir / (target + ext)
            if check_path.exists():
                return str(check_path.relative_to(self.current_dir))

        # Try in same directory as source
        source_dir = Path(source_path).parent
        for ext in [".md", ".txt", ""]:
            check_path = self.current_dir / source_dir / (target + ext)
            if check_path.exists():
                return str(check_path.relative_to(self.current_dir))

        # Try in common directories
        for subdir in ["semantic", "episodic", "procedural"]:
            for ext in [".md", ".txt", ""]:
                check_path = self.current_dir / subdir / (target + ext)
                if check_path.exists():
                    return str(check_path.relative_to(self.current_dir))

        return None

    def build_graph(
        self, include_similarity: bool = True, similarity_threshold: float = 0.7
    ) -> KnowledgeGraphData:
        """
        Build the knowledge graph from memory files.

        Args:
            include_similarity: Include similarity-based edges
            similarity_threshold: Minimum similarity for edges (0-1)

        Returns:
            KnowledgeGraphData with nodes and edges
        """
        nodes = []
        edges = []
        file_paths = []
        file_contents = {}
        file_tags = defaultdict(list)

        # Collect all memory files
        if not self.current_dir.exists():
            return KnowledgeGraphData(nodes=[], edges=[])

        for memory_file in self.current_dir.glob("**/*.md"):
            try:
                rel_path = str(memory_file.relative_to(self.current_dir))
                content = memory_file.read_text()

                # Create node
                memory_type = self._detect_memory_type(rel_path)
                tags = self._extract_tags_from_frontmatter(content)

                node = GraphNode(
                    id=rel_path,
                    label=memory_file.stem,
                    memory_type=memory_type,
                    size=len(content),
                    tags=tags,
                )
                nodes.append(node)
                file_paths.append(rel_path)
                file_contents[rel_path] = content

                # Index tags
                for tag in tags:
                    file_tags[tag].append(rel_path)

                # Add to NetworkX graph if available
                if self._graph is not None:
                    self._graph.add_node(rel_path, **node.to_dict())

            except Exception:
                continue

        # Add wikilink edges
        for source_path, content in file_contents.items():
            links = self._extract_wikilinks(content)
            for target in links:
                target_path = self._normalize_link_target(target, source_path)
                if target_path and target_path in file_contents:
                    edge = GraphEdge(
                        source=source_path, target=target_path, edge_type="reference", weight=1.0
                    )
                    edges.append(edge)

                    if self._graph is not None:
                        self._graph.add_edge(source_path, target_path, type="reference", weight=1.0)

        # Add tag-based edges
        for tag, files in file_tags.items():
            if len(files) > 1:
                for i, file1 in enumerate(files):
                    for file2 in files[i + 1 :]:
                        edge = GraphEdge(
                            source=file1, target=file2, edge_type="same_topic", weight=0.5
                        )
                        edges.append(edge)

                        if self._graph is not None:
                            self._graph.add_edge(file1, file2, type="same_topic", weight=0.5)

        # Add similarity edges
        if include_similarity and self.vector_store and len(file_paths) > 1:
            try:
                edges.extend(
                    self._build_similarity_edges(file_paths, file_contents, similarity_threshold)
                )
            except Exception:
                pass  # Skip similarity if vector store fails

        # Build metadata
        metadata = {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "memory_types": {
                "episodic": sum(1 for n in nodes if n.memory_type == "episodic"),
                "semantic": sum(1 for n in nodes if n.memory_type == "semantic"),
                "procedural": sum(1 for n in nodes if n.memory_type == "procedural"),
                "other": sum(
                    1 for n in nodes if n.memory_type not in ["episodic", "semantic", "procedural"]
                ),
            },
            "edge_types": {
                "reference": sum(1 for e in edges if e.edge_type == "reference"),
                "similarity": sum(1 for e in edges if e.edge_type == "similarity"),
                "same_topic": sum(1 for e in edges if e.edge_type == "same_topic"),
            },
        }

        return KnowledgeGraphData(nodes=nodes, edges=edges, metadata=metadata)

    def _build_similarity_edges(
        self, file_paths: List[str], file_contents: Dict[str, str], threshold: float
    ) -> List[GraphEdge]:
        """Build edges based on semantic similarity."""
        edges = []

        # Get embeddings for all files
        embeddings = {}
        for path, content in file_contents.items():
            try:
                # Use first 2000 chars for efficiency
                truncated = content[:2000]
                emb = self.vector_store._embed(truncated)
                embeddings[path] = emb
            except Exception:
                continue

        # Compute pairwise similarities
        import math

        def cosine_similarity(a: List[float], b: List[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(x * x for x in b))
            if norm_a == 0 or norm_b == 0:
                return 0
            return dot / (norm_a * norm_b)

        paths_list = list(embeddings.keys())
        for i, path1 in enumerate(paths_list):
            for path2 in paths_list[i + 1 :]:
                sim = cosine_similarity(embeddings[path1], embeddings[path2])
                if sim >= threshold:
                    edge = GraphEdge(source=path1, target=path2, edge_type="similarity", weight=sim)
                    edges.append(edge)

                    if self._graph is not None:
                        self._graph.add_edge(path1, path2, type="similarity", weight=sim)

        return edges

    def find_isolated_nodes(self) -> List[str]:
        """Find nodes with no connections (knowledge islands)."""
        if self._graph is None or len(self._graph) == 0:
            return []

        # Convert to undirected for analysis
        undirected = self._graph.to_undirected()
        return [node for node in undirected.nodes() if undirected.degree(node) == 0]

    def find_potential_contradictions(self) -> List[Tuple[str, str, float]]:
        """
        Find files that might have contradictory information.

        Returns files in the same topic cluster with low similarity.
        """
        if self._graph is None:
            return []

        contradictions = []

        # Files connected by same_topic but with low similarity
        for u, v, data in self._graph.edges(data=True):
            if data.get("type") == "same_topic":
                # Check if there's also a similarity edge
                sim_edge = self._graph.get_edge_data(u, v)
                if sim_edge and sim_edge.get("type") == "similarity":
                    if sim_edge.get("weight", 1.0) < 0.3:
                        contradictions.append((u, v, sim_edge.get("weight", 0)))

        return contradictions

    def export_for_d3(self) -> str:
        """Export graph in D3.js force-graph format."""
        graph_data = self.build_graph()

        d3_format = {
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
        }

        return json.dumps(d3_format, indent=2)
