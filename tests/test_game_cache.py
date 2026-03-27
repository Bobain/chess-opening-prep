"""Tests for game cache: merge, fetch, and unified list behavior."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import chess.pgn

from chess_self_coach.game_cache import fetch_and_cache_games, get_unified_game_list


def _make_pgn_game(game_id: str, white: str, black: str, date: str) -> chess.pgn.Game:
    """Create a minimal PGN game for testing."""
    game = chess.pgn.Game()
    game.headers["White"] = white
    game.headers["Black"] = black
    game.headers["Date"] = date
    game.headers["Result"] = "1-0"
    game.headers["Link"] = game_id
    game.headers["Event"] = "Live Chess"
    game.add_variation(chess.Move.from_uci("e2e4"))
    return game


def _seed_cache(tmp_path: Path, games: list[dict]) -> None:
    """Write a fetched_games.json cache file."""
    cache_games = {}
    for g in games:
        cache_games[g["game_id"]] = {
            "pgn": f'[White "{g["white"]}"]\n[Black "{g["black"]}"]\n[Date "{g["date"]}"]\n[Result "1-0"]\n[Link "{g["game_id"]}"]\n\n1. e4 *\n',
            "headers": {
                "White": g["white"],
                "Black": g["black"],
                "Date": g["date"],
                "Result": "1-0",
                "Link": g["game_id"],
            },
            "player_color": "white",
            "move_count": 1,
            "source": "chess.com",
        }
    cache = {"fetched_at": "2026-03-27T00:00:00+00:00", "games": cache_games}
    (tmp_path / "fetched_games.json").write_text(json.dumps(cache))


@patch("chess_self_coach.game_cache._find_project_root")
@patch("chess_self_coach.importer.fetch_lichess_games", return_value=[])
def test_merge_preserves_existing_cache(mock_lichess, mock_root, tmp_path):
    """Fetching new games preserves previously cached games."""
    mock_root.return_value = tmp_path

    # Seed cache with 2 old games
    _seed_cache(tmp_path, [
        {"game_id": "https://chess.com/game/1", "white": "Player", "black": "Old1", "date": "2026.01.01"},
        {"game_id": "https://chess.com/game/2", "white": "Player", "black": "Old2", "date": "2026.01.02"},
    ])

    # Fetch returns 1 new game + 1 duplicate
    new_game = _make_pgn_game("https://chess.com/game/3", "Player", "New1", "2026.03.01")
    dup_game = _make_pgn_game("https://chess.com/game/1", "Player", "Old1", "2026.01.01")

    with patch("chess_self_coach.importer.fetch_chesscom_games", return_value=[new_game, dup_game]):
        summaries = fetch_and_cache_games("", "Player", max_games=10)

    # Cache should have 3 games total (2 old + 1 new)
    cache = json.loads((tmp_path / "fetched_games.json").read_text())
    assert len(cache["games"]) == 3
    assert "https://chess.com/game/1" in cache["games"]
    assert "https://chess.com/game/2" in cache["games"]
    assert "https://chess.com/game/3" in cache["games"]

    # Summaries should include all 3 games
    assert len(summaries) == 3


@patch("chess_self_coach.game_cache._find_project_root")
@patch("chess_self_coach.importer.fetch_lichess_games", return_value=[])
def test_fetch_count_includes_cache_size(mock_lichess, mock_root, tmp_path):
    """fetch_count passed to API = max_games + cached_count."""
    mock_root.return_value = tmp_path

    # Seed cache with 5 games
    _seed_cache(tmp_path, [
        {"game_id": f"https://chess.com/game/{i}", "white": "P", "black": f"O{i}", "date": f"2026.01.0{i}"}
        for i in range(1, 6)
    ])

    captured_max = {}

    def fake_chesscom(username, max_games):
        captured_max["value"] = max_games
        return []

    with patch("chess_self_coach.importer.fetch_chesscom_games", side_effect=fake_chesscom):
        fetch_and_cache_games("", "Player", max_games=10)

    # Should request 10 + 5 = 15 games from the API
    assert captured_max["value"] == 15


@patch("chess_self_coach.game_cache._find_project_root")
@patch("chess_self_coach.importer.fetch_lichess_games", return_value=[])
def test_unified_list_includes_cached_only_games(mock_lichess, mock_root, tmp_path):
    """get_unified_game_list returns cached-but-not-analyzed games."""
    mock_root.return_value = tmp_path

    # Seed cache with 3 games, no analysis_data.json
    _seed_cache(tmp_path, [
        {"game_id": f"https://chess.com/game/{i}", "white": "P", "black": f"O{i}", "date": f"2026.01.0{i}"}
        for i in range(1, 4)
    ])
    # Empty analysis_data.json
    (tmp_path / "analysis_data.json").write_text(json.dumps({"version": 1, "games": {}}))

    summaries = get_unified_game_list(limit=9999)
    assert len(summaries) == 3
    assert all(not s.analyzed for s in summaries)


@patch("chess_self_coach.game_cache._find_project_root")
@patch("chess_self_coach.importer.fetch_lichess_games", return_value=[])
def test_fetch_latest_adds_new_recent_games(mock_lichess, mock_root, tmp_path):
    """'Fetch latest' adds newly played games not yet in cache."""
    mock_root.return_value = tmp_path

    # Seed cache with 2 games
    _seed_cache(tmp_path, [
        {"game_id": "https://chess.com/game/1", "white": "P", "black": "O1", "date": "2026.03.25"},
        {"game_id": "https://chess.com/game/2", "white": "P", "black": "O2", "date": "2026.03.26"},
    ])

    # API returns 3 games: 2 cached + 1 brand new
    games = [
        _make_pgn_game("https://chess.com/game/NEW", "P", "NewOpp", "2026.03.27"),
        _make_pgn_game("https://chess.com/game/2", "P", "O2", "2026.03.26"),
        _make_pgn_game("https://chess.com/game/1", "P", "O1", "2026.03.25"),
    ]

    with patch("chess_self_coach.importer.fetch_chesscom_games", return_value=games):
        summaries = fetch_and_cache_games("", "P", max_games=200)

    cache = json.loads((tmp_path / "fetched_games.json").read_text())
    assert len(cache["games"]) == 3
    assert "https://chess.com/game/NEW" in cache["games"]


@patch("chess_self_coach.game_cache._find_project_root")
@patch("chess_self_coach.importer.fetch_lichess_games", return_value=[])
def test_fetch_n_adds_older_games(mock_lichess, mock_root, tmp_path):
    """'Fetch N games' with large N adds older games beyond cache."""
    mock_root.return_value = tmp_path

    # Seed cache with 2 recent games
    _seed_cache(tmp_path, [
        {"game_id": "https://chess.com/game/recent1", "white": "P", "black": "R1", "date": "2026.03.26"},
        {"game_id": "https://chess.com/game/recent2", "white": "P", "black": "R2", "date": "2026.03.25"},
    ])

    # API returns 4 games: 2 cached + 2 older (because we asked for max_games+cached)
    games = [
        _make_pgn_game("https://chess.com/game/recent1", "P", "R1", "2026.03.26"),
        _make_pgn_game("https://chess.com/game/recent2", "P", "R2", "2026.03.25"),
        _make_pgn_game("https://chess.com/game/old1", "P", "Old1", "2026.02.15"),
        _make_pgn_game("https://chess.com/game/old2", "P", "Old2", "2026.02.10"),
    ]

    with patch("chess_self_coach.importer.fetch_chesscom_games", return_value=games):
        summaries = fetch_and_cache_games("", "P", max_games=2)

    cache = json.loads((tmp_path / "fetched_games.json").read_text())
    # Should have 4 total: 2 cached + 2 new older
    assert len(cache["games"]) == 4
    assert "https://chess.com/game/old1" in cache["games"]
    assert "https://chess.com/game/old2" in cache["games"]

    # Summaries should include all 4
    assert len(summaries) == 4
