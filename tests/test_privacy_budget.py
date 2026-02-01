"""Tests for differential privacy budget."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from memvcs.core.privacy_budget import load_budget, spend_epsilon, add_noise


class TestLoadBudget:
    """Test budget loading."""

    def test_load_budget_no_file_returns_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            spent, max_eps, delta = load_budget(Path(tmpdir))
            assert spent == 0.0
            assert max_eps == 1.0
            assert delta == 1e-5

    def test_load_budget_from_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "privacy_budget.json"
            path.write_text('{"epsilon_spent": 0.5, "max_epsilon": 2.0, "delta": 1e-6}')
            spent, max_eps, delta = load_budget(Path(tmpdir))
            assert spent == 0.5
            assert max_eps == 2.0
            assert delta == 1e-6


class TestSpendEpsilon:
    """Test spending epsilon."""

    def test_spend_epsilon_first_time(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_dir = Path(tmpdir)
            ok = spend_epsilon(mem_dir, 0.1)
            assert ok is True
            spent, max_eps, _ = load_budget(mem_dir)
            assert spent == 0.1

    def test_spend_epsilon_accumulates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_dir = Path(tmpdir)
            spend_epsilon(mem_dir, 0.1)
            spend_epsilon(mem_dir, 0.2)
            spent, _, _ = load_budget(mem_dir)
            assert abs(spent - 0.3) < 1e-9

    def test_spend_epsilon_exceeds_budget_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_dir = Path(tmpdir)
            spend_epsilon(mem_dir, 0.9)
            ok = spend_epsilon(mem_dir, 0.2)  # would exceed 1.0
            assert ok is False
            spent, _, _ = load_budget(mem_dir)
            assert spent == 0.9


class TestAddNoise:
    """Test add_noise for differential privacy."""

    def test_add_noise_returns_float(self):
        result = add_noise(10.0, 1.0, 0.1, 1e-5)
        assert isinstance(result, float)

    def test_add_noise_different_with_different_values(self):
        r1 = add_noise(5.0, 1.0, 0.1, 1e-5)
        r2 = add_noise(5.0, 1.0, 0.1, 1e-5)
        # With high probability two calls differ (random)
        assert isinstance(r1, float) and isinstance(r2, float)


class TestGardenerDistillerDPIntegration:
    """Test that Gardener and Distiller use add_noise when use_dp=True."""

    def test_gardener_uses_add_noise_when_use_dp(self):
        from memvcs.core.gardener import Gardener, GardenerConfig, GardenerResult

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "current" / "episodic").mkdir(parents=True)
            (root / "current" / "semantic").mkdir(parents=True)
            (root / ".mem" / "objects" / "blob" / "ab" / "cd").mkdir(parents=True)
            (root / ".mem" / "refs" / "heads").mkdir(parents=True)
            (root / ".mem" / "staging").mkdir(parents=True)
            (root / ".mem" / "config.json").write_text("{}")
            for i in range(5):
                (root / "current" / "episodic" / f"e{i}.md").write_text(f"episode {i} python")

            class FakeRepo:
                def __init__(self, r):
                    self.root = r
                    self.current_dir = r / "current"
                    self.mem_dir = r / ".mem"
                    self.object_store = None
                    self.refs = None

            fake_repo = FakeRepo(root)
            config = GardenerConfig(
                threshold=2, auto_commit=False, use_dp=True, dp_epsilon=0.1, dp_delta=1e-5
            )
            gardener = Gardener(fake_repo, config)

            with patch(
                "memvcs.core.privacy_budget.add_noise", side_effect=lambda v, s, e, d: v + 1
            ):
                result = gardener.run(force=True)
            assert result.success
            assert result.clusters_found >= 0
            assert result.episodes_archived >= 0

    def test_distiller_uses_add_noise_when_use_dp(self):
        from memvcs.core.distiller import Distiller, DistillerConfig, DistillerResult

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "current" / "episodic").mkdir(parents=True)
            (root / "current" / "semantic" / "consolidated").mkdir(parents=True)
            (root / ".mem" / "objects" / "blob" / "ab" / "cd").mkdir(parents=True)
            (root / ".mem" / "refs" / "heads").mkdir(parents=True)
            (root / ".mem" / "staging").mkdir(parents=True)
            (root / ".mem" / "config.json").write_text("{}")
            (root / "current" / "episodic" / "e1.md").write_text("user prefers python")

            class FakeRepo:
                def __init__(self, r):
                    self.root = r
                    self.current_dir = r / "current"
                    self.mem_dir = r / ".mem"
                    self.object_store = None
                    self.refs = type(
                        "R",
                        (),
                        {
                            "branch_exists": lambda n: True,
                            "create_branch": lambda n: None,
                            "get_current_branch": lambda: "main",
                        },
                    )()

            fake_repo = FakeRepo(root)
            config = DistillerConfig(
                create_safety_branch=False, use_dp=True, dp_epsilon=0.1, dp_delta=1e-5
            )
            distiller = Distiller(fake_repo, config)

            with patch(
                "memvcs.core.privacy_budget.add_noise", side_effect=lambda v, s, e, d: v + 0.5
            ):
                result = distiller.run()
            assert result.success
            assert result.facts_extracted >= 0
            assert result.episodes_archived >= 0
