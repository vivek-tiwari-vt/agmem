"""Tests for differential privacy budget."""

import pytest
import tempfile
from pathlib import Path

from memvcs.core.privacy_budget import load_budget, spend_epsilon


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
