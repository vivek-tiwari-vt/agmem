"""
Tests for Phase 3 features: Time-Travel, Private Search, Semantic Graph, Agents.
"""

import pytest
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from memvcs.core.repository import Repository


@pytest.fixture
def test_repo():
    """Create a test repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        repo = Repository.init(repo_path, author_name="Test", author_email="test@example.com")
        
        # Create some test files
        (repo.current_dir / "episodic").mkdir(parents=True, exist_ok=True)
        (repo.current_dir / "semantic").mkdir(parents=True, exist_ok=True)
        (repo.current_dir / "episodic" / "session1.md").write_text("# Session 1\n\nTest content about Python")
        (repo.current_dir / "semantic" / "concepts.md").write_text("# Concepts\n\n#python #programming")
        
        yield repo


# --- Time-Travel Tests ---

class TestTimeExpressionParser:
    """Test TimeExpressionParser."""

    def test_parse_relative(self):
        """Test parsing relative expressions."""
        from memvcs.core.timetravel import TimeExpressionParser

        parser = TimeExpressionParser()
        
        result = parser.parse("2 days ago")
        assert result.is_relative is True
        
        now = datetime.now(timezone.utc)
        expected = now - timedelta(days=2)
        assert abs((result.resolved_time - expected).total_seconds()) < 60

    def test_parse_iso_date(self):
        """Test parsing ISO dates."""
        from memvcs.core.timetravel import TimeExpressionParser

        parser = TimeExpressionParser()
        result = parser.parse("2024-01-15")
        
        assert result.is_relative is False
        assert result.resolved_time.year == 2024
        assert result.resolved_time.day == 15

    def test_parse_range(self):
        """Test parsing range expressions."""
        from memvcs.core.timetravel import TimeExpressionParser

        parser = TimeExpressionParser()
        result = parser.parse("last 7 days")
        
        assert result.is_range is True
        assert result.range_end is not None


class TestTemporalNavigator:
    """Test TemporalNavigator."""

    def test_find_commits_in_range(self, test_repo):
        """Test finding commits in range."""
        from memvcs.core.timetravel import TemporalNavigator

        # Make a commit
        test_repo.stage_file("episodic/session1.md")
        test_repo.commit("Test commit")

        navigator = TemporalNavigator(test_repo.root)
        commits = navigator.find_commits_in_range("7 days ago", "now")
        
        assert len(commits) >= 1


class TestTimelineVisualizer:
    """Test TimelineVisualizer."""

    def test_get_activity_timeline(self, test_repo):
        """Test getting activity timeline."""
        from memvcs.core.timetravel import TimelineVisualizer

        # Make commits
        test_repo.stage_file("episodic/session1.md")
        test_repo.commit("Commit 1")

        visualizer = TimelineVisualizer(test_repo.root)
        timeline = visualizer.get_activity_timeline(days=30)
        
        assert isinstance(timeline, list)


# --- Private Search Tests ---

class TestSearchTokenizer:
    """Test SearchTokenizer."""

    def test_tokenize(self):
        """Test tokenization."""
        from memvcs.core.private_search import SearchTokenizer

        tokenizer = SearchTokenizer()
        tokens = tokenizer.tokenize("Hello World Test")
        
        assert "hello" in tokens
        assert "world" in tokens

    def test_hash_token(self):
        """Test token hashing."""
        from memvcs.core.private_search import SearchTokenizer

        tokenizer = SearchTokenizer()
        hash1 = tokenizer.hash_token("hello")
        hash2 = tokenizer.hash_token("hello")
        hash3 = tokenizer.hash_token("world")
        
        assert hash1 == hash2
        assert hash1 != hash3


class TestAccessControl:
    """Test AccessControl."""

    def test_set_and_check_access(self, test_repo):
        """Test setting and checking access."""
        from memvcs.core.private_search import AccessControl

        acl = AccessControl(test_repo.mem_dir)
        acl.set_file_access("secret.md", ["user1"], privacy_level="secret")

        assert acl.can_access("secret.md", "user1", "secret") is True
        assert acl.can_access("secret.md", "user2", "normal") is False


class TestPrivateSearchEngine:
    """Test PrivateSearchEngine."""

    def test_search(self, test_repo):
        """Test private search."""
        from memvcs.core.private_search import PrivateSearchEngine, SearchQuery

        engine = PrivateSearchEngine(test_repo.mem_dir, test_repo.current_dir)
        query = SearchQuery(
            query="Python",
            requester_id="user1",
            privacy_level="normal",
            include_content=True,
        )
        
        results = engine.search(query)
        assert isinstance(results, list)


# --- Semantic Graph Tests ---

class TestSemanticGraphBuilder:
    """Test SemanticGraphBuilder."""

    def test_build_graph(self, test_repo):
        """Test building semantic graph."""
        from memvcs.core.semantic_graph import SemanticGraphBuilder

        builder = SemanticGraphBuilder(test_repo.root)
        nodes, edges = builder.build_graph()
        
        assert len(nodes) >= 2


class TestSemanticClusterer:
    """Test SemanticClusterer."""

    def test_cluster_by_type(self, test_repo):
        """Test clustering by type."""
        from memvcs.core.semantic_graph import SemanticGraphBuilder, SemanticClusterer

        builder = SemanticGraphBuilder(test_repo.root)
        nodes, edges = builder.build_graph()
        
        clusterer = SemanticClusterer(nodes, edges)
        clusters = clusterer.cluster_by_type()
        
        assert "episodic" in clusters or "semantic" in clusters


class TestGraphSearchEngine:
    """Test GraphSearchEngine."""

    def test_search_by_tags(self, test_repo):
        """Test searching by tags."""
        from memvcs.core.semantic_graph import SemanticGraphBuilder, GraphSearchEngine

        builder = SemanticGraphBuilder(test_repo.root)
        nodes, edges = builder.build_graph()
        
        nodes_dict = {n.node_id: n for n in nodes}
        engine = GraphSearchEngine(nodes_dict, edges)
        
        results = engine.search_by_tags(["python"])
        assert isinstance(results, list)


# --- Agent Tests ---

class TestConsolidationAgent:
    """Test ConsolidationAgent."""

    def test_find_candidates(self, test_repo):
        """Test finding consolidation candidates."""
        from memvcs.core.agents import ConsolidationAgent

        agent = ConsolidationAgent(test_repo.root)
        candidates = agent.find_consolidation_candidates()
        
        assert isinstance(candidates, list)


class TestCleanupAgent:
    """Test CleanupAgent."""

    def test_find_duplicates(self, test_repo):
        """Test finding duplicates."""
        from memvcs.core.agents import CleanupAgent

        # Create duplicate files
        (test_repo.current_dir / "episodic" / "dup1.md").write_text("same content")
        (test_repo.current_dir / "episodic" / "dup2.md").write_text("same content")

        agent = CleanupAgent(test_repo.root)
        duplicates = agent.find_duplicates()
        
        assert len(duplicates) >= 1


class TestAlertAgent:
    """Test AlertAgent."""

    def test_add_and_get_alerts(self, test_repo):
        """Test adding and getting alerts."""
        from memvcs.core.agents import AlertAgent

        agent = AlertAgent(test_repo.root)
        agent.add_alert("test", "Test alert", severity="info")
        
        alerts = agent.get_alerts()
        assert len(alerts) >= 1

    def test_acknowledge_alert(self, test_repo):
        """Test acknowledging alerts."""
        from memvcs.core.agents import AlertAgent

        agent = AlertAgent(test_repo.root)
        alert = agent.add_alert("test", "Test alert")
        
        result = agent.acknowledge_alert(alert["id"])
        assert result is True


class TestMemoryAgentManager:
    """Test MemoryAgentManager."""

    def test_health_check(self, test_repo):
        """Test health check."""
        from memvcs.core.agents import MemoryAgentManager

        manager = MemoryAgentManager(test_repo.root)
        health = manager.run_health_check()
        
        assert "checks" in health
        assert "consolidation" in health["checks"]
        assert "cleanup" in health["checks"]
