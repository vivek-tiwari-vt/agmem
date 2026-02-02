"""
Tests for Multi-Agent Collaboration features.
"""

import json
import pytest
import tempfile
from pathlib import Path

from memvcs.core.repository import Repository


@pytest.fixture
def test_repo():
    """Create a test repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        repo = Repository.init(repo_path, author_name="Test", author_email="test@example.com")
        yield repo


class TestAgent:
    """Test Agent dataclass."""

    def test_agent_create(self):
        """Test creating an agent."""
        from memvcs.core.collaboration import Agent

        agent = Agent(
            agent_id="agent-123",
            name="TestAgent",
            public_key="ssh-rsa AAAA...",
        )

        assert agent.agent_id == "agent-123"
        assert agent.name == "TestAgent"

    def test_agent_roundtrip(self):
        """Test agent serialization."""
        from memvcs.core.collaboration import Agent

        agent = Agent(
            agent_id="agent-123",
            name="TestAgent",
            metadata={"type": "assistant"},
        )

        data = agent.to_dict()
        agent2 = Agent.from_dict(data)

        assert agent.agent_id == agent2.agent_id
        assert agent.name == agent2.name
        assert agent.metadata == agent2.metadata


class TestAgentRegistry:
    """Test AgentRegistry class."""

    def test_register_agent(self, test_repo):
        """Test registering an agent."""
        from memvcs.core.collaboration import AgentRegistry

        registry = AgentRegistry(test_repo.mem_dir)
        agent = registry.register_agent("Claude", metadata={"model": "claude-3"})

        assert agent.agent_id is not None
        assert agent.name == "Claude"

    def test_get_agent(self, test_repo):
        """Test getting an agent."""
        from memvcs.core.collaboration import AgentRegistry

        registry = AgentRegistry(test_repo.mem_dir)
        agent = registry.register_agent("Claude")

        retrieved = registry.get_agent(agent.agent_id)
        assert retrieved is not None
        assert retrieved.name == "Claude"

    def test_list_agents(self, test_repo):
        """Test listing agents."""
        from memvcs.core.collaboration import AgentRegistry

        registry = AgentRegistry(test_repo.mem_dir)
        registry.register_agent("Agent1")
        registry.register_agent("Agent2")

        agents = registry.list_agents()
        assert len(agents) == 2

    def test_remove_agent(self, test_repo):
        """Test removing an agent."""
        from memvcs.core.collaboration import AgentRegistry

        registry = AgentRegistry(test_repo.mem_dir)
        agent = registry.register_agent("ToRemove")

        result = registry.remove_agent(agent.agent_id)
        assert result is True
        assert registry.get_agent(agent.agent_id) is None


class TestTrustManager:
    """Test TrustManager class."""

    def test_grant_trust(self, test_repo):
        """Test granting trust between agents."""
        from memvcs.core.collaboration import TrustManager

        trust_mgr = TrustManager(test_repo.mem_dir)
        relation = trust_mgr.grant_trust(
            from_agent="agent-1",
            to_agent="agent-2",
            trust_level="full",
            reason="Verified partner",
        )

        assert relation.trust_level == "full"
        assert relation.from_agent == "agent-1"
        assert relation.to_agent == "agent-2"

    def test_get_trust_level(self, test_repo):
        """Test getting trust level."""
        from memvcs.core.collaboration import TrustManager

        trust_mgr = TrustManager(test_repo.mem_dir)
        trust_mgr.grant_trust("agent-1", "agent-2", "partial")

        level = trust_mgr.get_trust_level("agent-1", "agent-2")
        assert level == "partial"

        # Non-existent relation should return "none"
        level = trust_mgr.get_trust_level("agent-1", "agent-3")
        assert level == "none"

    def test_revoke_trust(self, test_repo):
        """Test revoking trust."""
        from memvcs.core.collaboration import TrustManager

        trust_mgr = TrustManager(test_repo.mem_dir)
        trust_mgr.grant_trust("agent-1", "agent-2", "full")

        result = trust_mgr.revoke_trust("agent-1", "agent-2")
        assert result is True

        level = trust_mgr.get_trust_level("agent-1", "agent-2")
        assert level == "none"

    def test_get_trust_graph(self, test_repo):
        """Test getting trust graph for visualization."""
        from memvcs.core.collaboration import TrustManager

        trust_mgr = TrustManager(test_repo.mem_dir)
        trust_mgr.grant_trust("a", "b", "full")
        trust_mgr.grant_trust("b", "c", "partial")

        graph = trust_mgr.get_trust_graph()
        assert "nodes" in graph
        assert "links" in graph
        assert len(graph["nodes"]) == 3
        assert len(graph["links"]) == 2


class TestContributionTracker:
    """Test ContributionTracker class."""

    def test_record_contribution(self, test_repo):
        """Test recording a contribution."""
        from memvcs.core.collaboration import ContributionTracker

        tracker = ContributionTracker(test_repo.mem_dir)
        contrib = tracker.record_contribution(
            agent_id="agent-1",
            commit_hash="abc123",
            files_changed=5,
            additions=100,
            deletions=20,
        )

        assert contrib.agent_id == "agent-1"
        assert contrib.files_changed == 5

    def test_get_contributions(self, test_repo):
        """Test getting contributions by agent."""
        from memvcs.core.collaboration import ContributionTracker

        tracker = ContributionTracker(test_repo.mem_dir)
        tracker.record_contribution("agent-1", "abc", 3, 50, 10)
        tracker.record_contribution("agent-1", "def", 2, 30, 5)
        tracker.record_contribution("agent-2", "ghi", 1, 10, 0)

        contribs = tracker.get_contributions("agent-1")
        assert len(contribs) == 2

    def test_get_leaderboard(self, test_repo):
        """Test getting contributor leaderboard."""
        from memvcs.core.collaboration import ContributionTracker

        tracker = ContributionTracker(test_repo.mem_dir)
        tracker.record_contribution("agent-1", "a", 5, 100, 20)
        tracker.record_contribution("agent-1", "b", 3, 50, 10)
        tracker.record_contribution("agent-2", "c", 1, 10, 0)

        leaderboard = tracker.get_leaderboard()
        assert len(leaderboard) >= 2
        assert leaderboard[0]["agent_id"] == "agent-1"
        assert leaderboard[0]["commits"] == 2


class TestCollaborationDashboard:
    """Test collaboration dashboard helper."""

    def test_get_collaboration_dashboard(self, test_repo):
        """Test getting dashboard data."""
        from memvcs.core.collaboration import (
            AgentRegistry,
            TrustManager,
            ContributionTracker,
            get_collaboration_dashboard,
        )

        # Set up some data
        registry = AgentRegistry(test_repo.mem_dir)
        registry.register_agent("Agent1")

        trust_mgr = TrustManager(test_repo.mem_dir)
        trust_mgr.grant_trust("a", "b", "full")

        tracker = ContributionTracker(test_repo.mem_dir)
        tracker.record_contribution("a", "abc", 5, 100, 10)

        # Get dashboard
        dashboard = get_collaboration_dashboard(test_repo.mem_dir)

        assert "agents" in dashboard
        assert "trust_graph" in dashboard
        assert "leaderboard" in dashboard
        assert "recent_activity" in dashboard
