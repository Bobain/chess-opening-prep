"""Shared test fixtures for chess-self-coach."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chess_self_coach.config import CONFIG_FILE, DATA_DIR


def pytest_xdist_auto_num_workers(config):
    """Use N-1 cores for test parallelization (harmonized with trainer)."""
    from chess_self_coach import worker_count

    return worker_count()


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the tests/fixtures/ directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project structure with data/config.json, .env, and pgn/.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        Path to the temporary project root.
    """
    # pyproject.toml (project root marker)
    (tmp_path / "pyproject.toml").touch()

    # data/config.json
    data_dir = tmp_path / DATA_DIR
    data_dir.mkdir()
    config = {
        "stockfish": {
            "path": "/usr/games/stockfish",
            "expected_version": "Stockfish 18",
            "fallback_path": "/usr/games/stockfish",
        },
        "analysis": {"default_depth": 18, "blunder_threshold": 1.0},
    }
    (data_dir / CONFIG_FILE).write_text(json.dumps(config, indent=2))

    # .env
    (tmp_path / ".env").write_text("LICHESS_API_TOKEN=lip_test_token_12345\n")

    # pgn directory
    (tmp_path / "pgn").mkdir()

    return tmp_path
