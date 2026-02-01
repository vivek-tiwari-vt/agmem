"""
Distiller - Episodic-to-semantic distillation pipeline for agmem.

Converts session logs into compact facts (like memory consolidation during sleep).
Extends Gardener with factual extraction and safety branches.
"""

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

from .gardener import Gardener, GardenerConfig, EpisodeCluster


@dataclass
class DistillerConfig:
    """Configuration for the Distiller."""

    source_dir: str = "episodic"
    target_dir: str = "semantic/consolidated"
    archive_dir: str = "archive"
    min_cluster_size: int = 3
    extraction_confidence_threshold: float = 0.7
    safety_branch_prefix: str = "auto-distill/"
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    create_safety_branch: bool = True
    use_dp: bool = False
    dp_epsilon: Optional[float] = None
    dp_delta: Optional[float] = None


@dataclass
class DistillerResult:
    """Result of a distillation run."""

    success: bool
    clusters_processed: int
    facts_extracted: int
    episodes_archived: int
    branch_created: Optional[str] = None
    commit_hash: Optional[str] = None
    message: str = ""


class Distiller:
    """
    Distills episodic memory into semantic facts.

    Pipeline: cluster episodes -> extract facts via LLM -> merge with semantic -> archive.
    Creates safety branch for human review before merging to main.
    """

    def __init__(self, repo: Any, config: Optional[DistillerConfig] = None):
        self.repo = repo
        self.config = config or DistillerConfig()
        self.source_dir = repo.root / "current" / self.config.source_dir
        self.target_dir = repo.root / "current" / self.config.target_dir.rstrip("/")
        archive_candidate = repo.current_dir / self.config.archive_dir
        try:
            archive_candidate.resolve().relative_to(repo.current_dir.resolve())
            self.archive_dir = archive_candidate
        except (ValueError, RuntimeError):
            self.archive_dir = repo.current_dir / "archive"
        self.gardener = Gardener(
            repo,
            GardenerConfig(
                threshold=1,
                archive_dir=self.config.archive_dir,
                min_cluster_size=self.config.min_cluster_size,
                llm_provider=self.config.llm_provider,
                llm_model=self.config.llm_model,
            ),
        )

    def load_episodes_from(self, source_path: Path) -> List[Tuple[Path, str]]:
        """Load episodes from source directory."""
        episodes = []
        if not source_path.exists():
            return episodes
        for f in source_path.glob("**/*.md"):
            if f.is_file():
                try:
                    episodes.append((f, f.read_text(encoding="utf-8", errors="replace")))
                except Exception:
                    continue
        return episodes

    def cluster_episodes(self, episodes: List[Tuple[Path, str]]) -> List[EpisodeCluster]:
        """Cluster episodes using Gardener's logic."""
        try:
            return self.gardener.cluster_episodes_with_embeddings(episodes)
        except Exception:
            return self.gardener.cluster_episodes(episodes)

    def extract_facts(self, cluster: EpisodeCluster) -> List[str]:
        """Extract factual statements from cluster via LLM or heuristics."""
        contents = []
        for ep_path in cluster.episodes[:10]:
            try:
                contents.append(ep_path.read_text()[:1000])
            except Exception:
                continue
        combined = "\n---\n".join(contents)

        if self.config.llm_provider and self.config.llm_model:
            try:
                from .llm import get_provider

                config = {
                    "llm_provider": self.config.llm_provider,
                    "llm_model": self.config.llm_model,
                }
                provider = get_provider(config=config)
                if provider:
                    text = provider.complete(
                        [
                            {
                                "role": "system",
                                "content": "Extract factual statements from the text. Output as bullet points (one fact per line). Focus on: user preferences, learned facts, key decisions.",
                            },
                            {
                                "role": "user",
                                "content": f"Topic: {cluster.topic}\n\n{combined[:4000]}",
                            },
                        ],
                        max_tokens=500,
                    )
                    return [
                        line.strip() for line in text.splitlines() if line.strip().startswith("-")
                    ][:15]
            except Exception:
                pass

        # Fallback: simple extraction
        facts = []
        for line in combined.splitlines():
            line = line.strip()
            if len(line) > 20 and not line.startswith("#") and not line.startswith("-"):
                if any(w in line.lower() for w in ["prefers", "likes", "uses", "learned", "user"]):
                    facts.append(f"- {line[:200]}")
        return facts[:10] if facts else [f"- Learned about {cluster.topic}"]

    def write_consolidated(self, cluster: EpisodeCluster, facts: List[str]) -> Path:
        """Write consolidated semantic file."""
        self.target_dir.mkdir(parents=True, exist_ok=True)
        safe_topic = cluster.topic.replace(" ", "-").lower().replace("/", "_")[:30]
        ts = datetime.utcnow().strftime("%Y%m%d")
        filename = f"consolidated-{safe_topic}-{ts}.md"
        out_path = (self.target_dir / filename).resolve()
        try:
            out_path.relative_to(self.repo.current_dir.resolve())
        except ValueError:
            out_path = self.target_dir / f"consolidated-{ts}.md"

        confidence_score = self.config.extraction_confidence_threshold
        if self.config.use_dp and self.config.dp_epsilon is not None and self.config.dp_delta is not None:
            from .privacy_budget import add_noise
            confidence_score = add_noise(confidence_score, 0.1, self.config.dp_epsilon, self.config.dp_delta)
            confidence_score = max(0.0, min(1.0, confidence_score))
        frontmatter = {
            "schema_version": "1.0",
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "source_agent_id": "distiller",
            "memory_type": "semantic",
            "tags": cluster.tags + ["auto-generated", "consolidated"],
            "confidence_score": confidence_score,
        }
        body = f"# Consolidated: {cluster.topic}\n\n" + "\n".join(facts)
        if YAML_AVAILABLE:
            import yaml

            content = f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n\n{body}"
        else:
            content = body
        out_path.write_text(content)
        return out_path

    def archive_episodes(self, episodes: List[Path]) -> int:
        """Archive processed episodes to .mem/archive/."""
        archive_base = self.repo.mem_dir / "archive"
        archive_base.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        archive_sub = archive_base / ts
        archive_sub.mkdir(exist_ok=True)
        count = 0
        for ep in episodes:
            try:
                safe_name = ep.name.replace("..", "_").replace("/", "_")
                dest = (archive_sub / safe_name).resolve()
                dest.relative_to(archive_base.resolve())
                shutil.move(str(ep), str(dest))
                count += 1
            except (ValueError, Exception):
                continue
        return count

    def run(
        self,
        source: Optional[str] = None,
        target: Optional[str] = None,
        model: Optional[str] = None,
    ) -> DistillerResult:
        """Run distillation pipeline."""
        source_path = Path(source) if source else self.source_dir
        if not source_path.is_absolute():
            source_path = self.repo.root / "current" / source_path
        target_path = Path(target) if target else self.target_dir
        if not target_path.is_absolute():
            target_path = self.repo.root / "current" / target_path
        self.target_dir = target_path
        if model:
            self.config.llm_model = model

        episodes = self.load_episodes_from(source_path)
        if not episodes:
            return DistillerResult(
                success=True,
                clusters_processed=0,
                facts_extracted=0,
                episodes_archived=0,
                message="No episodes to process",
            )

        clusters = self.cluster_episodes(episodes)
        if not clusters:
            return DistillerResult(
                success=True,
                clusters_processed=0,
                facts_extracted=0,
                episodes_archived=0,
                message="No clusters formed",
            )

        # Create safety branch if configured
        branch_name = None
        if self.config.create_safety_branch:
            ts = datetime.utcnow().strftime("%Y-%m-%d")
            branch_name = f"{self.config.safety_branch_prefix}{ts}"
            if not self.repo.refs.branch_exists(branch_name):
                self.repo.refs.create_branch(branch_name)
                self.repo.checkout(branch_name, force=True)

        facts_count = 0
        all_archived = []
        for cluster in clusters:
            facts = self.extract_facts(cluster)
            self.write_consolidated(cluster, facts)
            facts_count += len(facts)
            all_archived.extend(cluster.episodes)

        archived = self.archive_episodes(all_archived)

        commit_hash = None
        if facts_count > 0:
            try:
                for f in self.target_dir.glob("consolidated-*.md"):
                    rel = str(f.relative_to(self.repo.root / "current"))
                    self.repo.stage_file(rel)
                commit_hash = self.repo.commit(
                    f"distiller: consolidated {facts_count} facts from {len(episodes)} episodes",
                    {"distiller": True, "clusters": len(clusters)},
                )
            except Exception:
                pass

        clusters_processed = len(clusters)
        facts_extracted = facts_count
        episodes_archived = archived
        if self.config.use_dp and self.config.dp_epsilon is not None and self.config.dp_delta is not None:
            from .privacy_budget import add_noise
            sensitivity = 1.0
            clusters_processed = max(0, int(round(add_noise(float(clusters_processed), sensitivity, self.config.dp_epsilon, self.config.dp_delta))))
            facts_extracted = max(0, int(round(add_noise(float(facts_extracted), sensitivity, self.config.dp_epsilon, self.config.dp_delta))))
            episodes_archived = max(0, int(round(add_noise(float(episodes_archived), sensitivity, self.config.dp_epsilon, self.config.dp_delta))))

        return DistillerResult(
            success=True,
            clusters_processed=clusters_processed,
            facts_extracted=facts_extracted,
            episodes_archived=episodes_archived,
            branch_created=branch_name,
            commit_hash=commit_hash,
            message=f"Processed {len(clusters)} clusters, extracted {facts_count} facts",
        )
