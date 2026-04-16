"""Tests for classify_game_single() — per-game move classification."""

from __future__ import annotations

import json
from pathlib import Path

from chess_self_coach.classifier import classify_game_single


def _make_game_data() -> dict:
    """Minimal game data with two moves that can be classified."""
    return {
        "player_color": "white",
        "headers": {"white": "player", "black": "opp"},
        "moves": [
            {
                "fen_before": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "fen_after": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                "move_san": "e4",
                "move_uci": "e2e4",
                "side": "white",
                "in_opening": True,
                "eval_before": {"score_cp": 20, "best_move_uci": "e2e4"},
                "eval_after": {"score_cp": -20},
                "cp_loss": 0,
            },
            {
                "fen_before": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                "fen_after": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
                "move_san": "e5",
                "move_uci": "e7e5",
                "side": "black",
                "in_opening": True,
                "eval_before": {"score_cp": -20, "best_move_uci": "e7e5"},
                "eval_after": {"score_cp": 20},
                "cp_loss": 0,
            },
        ],
    }


def test_classify_game_single_returns_list(tmp_path: Path):
    """Returns a list of classification dicts, one per move."""
    output = tmp_path / "classifications_data.json"
    game_data = _make_game_data()

    result = classify_game_single("g1", game_data, output_path=output)

    assert len(result) == 2


def test_classify_game_single_writes_file(tmp_path: Path):
    """Writes classifications_data.json with the game's classifications."""
    output = tmp_path / "classifications_data.json"
    game_data = _make_game_data()

    classify_game_single("g1", game_data, output_path=output)

    assert output.exists()
    data = json.loads(output.read_text())
    assert "g1" in data["games"]
    assert len(data["games"]["g1"]) == 2


def test_classify_game_single_incremental(tmp_path: Path):
    """Updating one game preserves other games in the file."""
    output = tmp_path / "classifications_data.json"

    existing = {"version": "1.0", "games": {"old_game": [{"c": "best", "s": "★", "co": "#96bc4b"}]}}
    output.write_text(json.dumps(existing))

    game_data = _make_game_data()
    classify_game_single("new_game", game_data, output_path=output)

    data = json.loads(output.read_text())
    assert "old_game" in data["games"]
    assert "new_game" in data["games"]
    assert data["games"]["old_game"] == [{"c": "best", "s": "★", "co": "#96bc4b"}]


def test_classify_game_single_with_tactics(tmp_path: Path):
    """Classification works when tactics data is provided."""
    output = tmp_path / "classifications_data.json"
    game_data = _make_game_data()
    tactics = [{"isFork": False, "isCheck": False}, {"isFork": False, "isCheck": False}]

    result = classify_game_single("g1", game_data, game_tactics=tactics, output_path=output)

    assert len(result) == 2
