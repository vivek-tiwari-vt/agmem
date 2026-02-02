"""Tests for Distiller differential privacy sampling."""

from pathlib import Path
import random
from unittest.mock import patch
import tempfile

from memvcs.core.distiller import Distiller, DistillerConfig


class FakeRepo:
    def __init__(self, root: Path):
        self.root = root
        self.current_dir = root / "current"


def _make_distiller(tmpdir: str) -> Distiller:
    root = Path(tmpdir)
    (root / "current").mkdir(parents=True, exist_ok=True)
    config = DistillerConfig(use_dp=True, dp_epsilon=0.1, dp_delta=1e-5)
    return Distiller(FakeRepo(root), config)


def test_apply_dp_to_facts_does_not_seed_random():
    with tempfile.TemporaryDirectory() as tmpdir:
        distiller = _make_distiller(tmpdir)
        facts = [f"- fact {i}" for i in range(10)]
        with patch("random.seed") as seed_mock:
            _ = distiller._apply_dp_to_facts(facts)
            seed_mock.assert_not_called()


def test_apply_dp_to_facts_respects_noisy_count():
    with tempfile.TemporaryDirectory() as tmpdir:
        distiller = _make_distiller(tmpdir)
        facts = [f"- fact {i}" for i in range(10)]
        with patch("memvcs.core.privacy_budget.add_noise", return_value=2.1):
            with patch("random.sample", wraps=random.sample) as sample_mock:
                sampled = distiller._apply_dp_to_facts(facts)
                assert len(sampled) == 2
                sample_mock.assert_called_once()
                call_args, call_kwargs = sample_mock.call_args
                if "k" in call_kwargs:
                    assert call_kwargs["k"] == 2
                else:
                    assert call_args[1] == 2


def test_apply_dp_to_facts_empty_returns_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        distiller = _make_distiller(tmpdir)
        assert distiller._apply_dp_to_facts([]) == []
