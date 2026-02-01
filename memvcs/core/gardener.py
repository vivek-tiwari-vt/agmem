"""
Gardener - The "Hindsight" reflection loop for agmem.

A background process that synthesizes raw episodic logs into semantic insights,
turning noise into wisdom over time.
"""

import os
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


@dataclass
class EpisodeCluster:
    """A cluster of related episodes."""

    topic: str
    episodes: List[Path]
    summary: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class GardenerConfig:
    """Configuration for the Gardener."""

    threshold: int = 50  # Number of episodic files before triggering
    archive_dir: str = "archive"
    min_cluster_size: int = 3
    max_clusters: int = 10
    llm_provider: Optional[str] = None  # "openai", "anthropic", etc.
    llm_model: Optional[str] = None
    auto_commit: bool = True


@dataclass
class GardenerResult:
    """Result of a gardener run."""

    success: bool
    clusters_found: int
    insights_generated: int
    episodes_archived: int
    commit_hash: Optional[str] = None
    message: str = ""


class Gardener:
    """
    The Gardener agent that refines memory over time.

    Wakes up when episodic/ files exceed a threshold, clusters them by topic,
    generates summaries, and archives the raw episodes.
    """

    def __init__(self, repo, config: Optional[GardenerConfig] = None):
        """
        Initialize the Gardener.

        Args:
            repo: Repository instance
            config: Optional configuration
        """
        self.repo = repo
        self.config = config or GardenerConfig()
        self.episodic_dir = repo.root / "current" / "episodic"
        self.semantic_dir = repo.root / "current" / "semantic"
        # Ensure archive_dir stays under current/ (path safety)
        try:
            archive_candidate = (repo.current_dir / self.config.archive_dir).resolve()
            archive_candidate.relative_to(repo.current_dir.resolve())
            self.archive_dir = archive_candidate
        except (ValueError, RuntimeError):
            self.archive_dir = repo.current_dir / "archive"

    def should_run(self) -> bool:
        """Check if the Gardener should run based on threshold."""
        if not self.episodic_dir.exists():
            return False

        episode_count = len(list(self.episodic_dir.glob("**/*.md")))
        return episode_count >= self.config.threshold

    def get_episode_count(self) -> int:
        """Get the current number of episodic files."""
        if not self.episodic_dir.exists():
            return 0
        return len(list(self.episodic_dir.glob("**/*.md")))

    def load_episodes(self) -> List[Tuple[Path, str]]:
        """
        Load all episodic files.

        Returns:
            List of (path, content) tuples
        """
        episodes = []

        if not self.episodic_dir.exists():
            return episodes

        for episode_file in self.episodic_dir.glob("**/*.md"):
            try:
                content = episode_file.read_text()
                episodes.append((episode_file, content))
            except Exception:
                continue

        return episodes

    def cluster_episodes(self, episodes: List[Tuple[Path, str]]) -> List[EpisodeCluster]:
        """
        Cluster episodes by topic using keyword analysis.

        For more sophisticated clustering, this could use embeddings with k-means.

        Args:
            episodes: List of (path, content) tuples

        Returns:
            List of EpisodeCluster objects
        """
        # Simple keyword-based clustering
        keyword_to_episodes: Dict[str, List[Path]] = defaultdict(list)

        # Common programming/tech keywords to look for
        keywords = [
            "python",
            "javascript",
            "typescript",
            "rust",
            "go",
            "error",
            "bug",
            "fix",
            "debug",
            "issue",
            "api",
            "database",
            "server",
            "client",
            "frontend",
            "backend",
            "test",
            "testing",
            "deploy",
            "deployment",
            "config",
            "setup",
            "install",
            "environment",
            "performance",
            "optimization",
            "memory",
            "cache",
            "security",
            "auth",
            "authentication",
            "permission",
            "user",
            "preference",
            "setting",
            "option",
        ]

        for path, content in episodes:
            content_lower = content.lower()
            found_keywords = []

            for keyword in keywords:
                if keyword in content_lower:
                    found_keywords.append(keyword)
                    keyword_to_episodes[keyword].append(path)

        # Create clusters from keywords with enough episodes
        clusters = []
        used_episodes = set()

        # Sort by number of episodes (descending)
        sorted_keywords = sorted(keyword_to_episodes.items(), key=lambda x: len(x[1]), reverse=True)

        for keyword, episode_paths in sorted_keywords:
            if len(clusters) >= self.config.max_clusters:
                break

            # Filter out already-used episodes
            unused_paths = [p for p in episode_paths if p not in used_episodes]

            if len(unused_paths) >= self.config.min_cluster_size:
                clusters.append(
                    EpisodeCluster(topic=keyword, episodes=unused_paths, tags=[keyword])
                )
                used_episodes.update(unused_paths)

        return clusters

    def cluster_episodes_with_embeddings(
        self, episodes: List[Tuple[Path, str]]
    ) -> List[EpisodeCluster]:
        """
        Cluster episodes using embeddings and k-means.

        Requires scikit-learn and sentence-transformers.
        """
        try:
            from sklearn.cluster import KMeans
            from sentence_transformers import SentenceTransformer
        except ImportError:
            # Fall back to keyword clustering
            return self.cluster_episodes(episodes)

        if len(episodes) < self.config.min_cluster_size:
            return []

        # Generate embeddings
        model = SentenceTransformer("all-MiniLM-L6-v2")
        texts = [content[:2000] for _, content in episodes]  # Truncate long texts
        embeddings = model.encode(texts)

        # Determine number of clusters
        n_clusters = min(self.config.max_clusters, len(episodes) // self.config.min_cluster_size)
        n_clusters = max(1, n_clusters)

        # Cluster
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        labels = kmeans.fit_predict(embeddings)

        # Group episodes by cluster
        cluster_episodes: Dict[int, List[Tuple[Path, str]]] = defaultdict(list)
        for i, (path, content) in enumerate(episodes):
            cluster_episodes[labels[i]].append((path, content))

        # Create cluster objects
        clusters = []
        for cluster_id, eps in cluster_episodes.items():
            if len(eps) >= self.config.min_cluster_size:
                # Extract topic from first few words of first episode
                first_content = eps[0][1]
                topic = self._extract_topic(first_content)

                clusters.append(EpisodeCluster(topic=topic, episodes=[p for p, _ in eps]))

        return clusters

    def _extract_topic(self, content: str) -> str:
        """Extract a topic label from content."""
        # Take first line or first 50 chars
        lines = content.strip().split("\n")
        first_line = lines[0] if lines else content[:50]

        # Clean up
        topic = first_line.strip("#").strip()
        if len(topic) > 50:
            topic = topic[:47] + "..."

        return topic or "general"

    def generate_summary(self, cluster: EpisodeCluster) -> str:
        """
        Generate a summary for a cluster of episodes.

        Uses LLM if configured, otherwise generates a simple summary.
        """
        # Collect content from episodes
        contents = []
        for episode_path in cluster.episodes[:10]:  # Limit to 10 episodes
            try:
                content = episode_path.read_text()
                contents.append(content[:1000])  # Truncate
            except Exception:
                continue

        combined = "\n---\n".join(contents)

        # Try LLM summarization (multi-provider)
        if self.config.llm_provider and self.config.llm_model:
            try:
                from .llm import get_provider
                config = {"llm_provider": self.config.llm_provider, "llm_model": self.config.llm_model}
                provider = get_provider(config=config)
                if provider:
                    return provider.complete(
                        [
                            {"role": "system", "content": "You are a helpful assistant that summarizes conversation logs into actionable insights."},
                            {"role": "user", "content": f"Summarize these conversation logs about '{topic}' into 2-3 key insights:\n\n{content[:4000]}"},
                        ],
                        max_tokens=500,
                    )
            except Exception:
                pass

        # Fall back to simple summary
        return self._simple_summary(cluster, contents)

    def _simple_summary(self, cluster: EpisodeCluster, contents: List[str]) -> str:
        """Generate a simple summary without LLM."""
        return f"""# Insights: {cluster.topic.title()}

**Summary**: The user had {len(cluster.episodes)} conversations related to {cluster.topic}.

**Common themes observed**:
- Multiple discussions about {cluster.topic}
- Recurring questions and patterns detected

**Generated**: {datetime.utcnow().isoformat()}Z

---
*This summary was auto-generated by the Gardener. Review and edit as needed.*
"""

    def write_insight(self, cluster: EpisodeCluster) -> Path:
        """
        Write cluster summary to semantic memory.

        Returns:
            Path to the written insight file
        """
        self.semantic_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename (sanitize topic to avoid path traversal)
        timestamp = datetime.utcnow().strftime("%Y%m%d")
        safe_topic = (
            cluster.topic.replace(" ", "-").lower().replace("/", "_").replace("\\", "_")[:30]
        )
        filename = f"insight-{safe_topic}-{timestamp}.md"
        insight_path = (self.semantic_dir / filename).resolve()
        try:
            insight_path.relative_to(self.repo.current_dir.resolve())
        except ValueError:
            insight_path = self.semantic_dir / f"insight-{timestamp}.md"

        # Generate frontmatter
        frontmatter = {
            "schema_version": "1.0",
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "source_agent_id": "gardener",
            "memory_type": "semantic",
            "tags": cluster.tags + ["auto-generated", "insight"],
            "source_episodes": len(cluster.episodes),
        }

        # Write file
        if YAML_AVAILABLE:
            import yaml

            content = (
                f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n\n{cluster.summary}"
            )
        else:
            content = cluster.summary

        insight_path.write_text(content)
        return insight_path

    def archive_episodes(self, episodes: List[Path]) -> int:
        """
        Archive processed episodes.

        Moves files to archive directory with timestamp prefix.

        Returns:
            Number of files archived
        """
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        archive_subdir = self.archive_dir / timestamp
        archive_subdir.mkdir(exist_ok=True)

        count = 0
        for episode_path in episodes:
            try:
                safe_name = (
                    episode_path.name.replace("..", "_").replace("/", "_").replace("\\", "_")
                )
                dest = (archive_subdir / safe_name).resolve()
                dest.relative_to(self.archive_dir.resolve())
                shutil.move(str(episode_path), str(dest))
                count += 1
            except (ValueError, Exception):
                continue

        return count

    def run(self, force: bool = False) -> GardenerResult:
        """
        Run the Gardener process.

        Args:
            force: Run even if threshold not met

        Returns:
            GardenerResult with operation details
        """
        if not force and not self.should_run():
            return GardenerResult(
                success=True,
                clusters_found=0,
                insights_generated=0,
                episodes_archived=0,
                message=f"Threshold not met ({self.get_episode_count()}/{self.config.threshold} episodes)",
            )

        # Load episodes
        episodes = self.load_episodes()
        if not episodes:
            return GardenerResult(
                success=True,
                clusters_found=0,
                insights_generated=0,
                episodes_archived=0,
                message="No episodes to process",
            )

        # Cluster episodes
        try:
            clusters = self.cluster_episodes_with_embeddings(episodes)
        except Exception:
            clusters = self.cluster_episodes(episodes)

        if not clusters:
            return GardenerResult(
                success=True,
                clusters_found=0,
                insights_generated=0,
                episodes_archived=0,
                message="No clusters could be formed",
            )

        # Generate summaries and write insights
        insights_written = 0
        all_archived_episodes = []

        for cluster in clusters:
            try:
                # Generate summary
                cluster.summary = self.generate_summary(cluster)

                # Write insight
                self.write_insight(cluster)
                insights_written += 1

                # Track episodes to archive
                all_archived_episodes.extend(cluster.episodes)
            except Exception as e:
                print(f"Warning: Failed to process cluster '{cluster.topic}': {e}")

        # Archive processed episodes
        archived_count = self.archive_episodes(all_archived_episodes)

        # Auto-commit if configured
        commit_hash = None
        if self.config.auto_commit and insights_written > 0:
            try:
                # Stage new insights
                for insight_file in self.semantic_dir.glob("insight-*.md"):
                    rel_path = str(insight_file.relative_to(self.repo.root / "current"))
                    self.repo.stage_file(f"current/{rel_path}")

                # Commit
                commit_hash = self.repo.commit(
                    f"gardener: synthesized {insights_written} insights from {archived_count} episodes",
                    {"gardener": True, "clusters": len(clusters)},
                )
            except Exception as e:
                print(f"Warning: Auto-commit failed: {e}")

        return GardenerResult(
            success=True,
            clusters_found=len(clusters),
            insights_generated=insights_written,
            episodes_archived=archived_count,
            commit_hash=commit_hash,
            message=f"Processed {len(clusters)} clusters, generated {insights_written} insights",
        )
