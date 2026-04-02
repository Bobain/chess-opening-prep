"""Tests for the local Lichess cloud evaluation database module."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from chess_self_coach.cloud_eval_db import (
    _short_fen,
    cloud_eval_db_status,
    find_cloud_eval_db,
    lookup_cloud_eval,
)


# --- _short_fen ---


def test_short_fen_strips_counters():
    """6-field FEN is trimmed to 4 fields."""
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    assert _short_fen(fen) == "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3"


def test_short_fen_already_short():
    """4-field FEN passes through unchanged."""
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3"
    assert _short_fen(fen) == fen


# --- find_cloud_eval_db ---


def test_find_cloud_eval_db_config(tmp_path: Path):
    """Config path takes priority over search paths."""
    db = tmp_path / "custom.db"
    db.touch()
    config = {"cloud_eval_db": {"path": str(db)}}
    assert find_cloud_eval_db(config) == db


def test_find_cloud_eval_db_none():
    """Returns None when no DB exists at any search path."""
    config = {"cloud_eval_db": {"path": "/nonexistent/cloud_eval.db"}}
    with patch("chess_self_coach.cloud_eval_db._SEARCH_PATHS", []):
        assert find_cloud_eval_db(config) is None


# --- Helper: create a test DB ---


def _make_test_db(tmp_path: Path, rows: list[tuple[str, list]]) -> Path:
    """Create a SQLite cloud eval DB with given rows.

    Args:
        tmp_path: Temporary directory for the DB file.
        rows: List of (fen, evals_list) tuples.

    Returns:
        Path to the created database.
    """
    db_path = tmp_path / "cloud_eval.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE cloud_eval (
            fen TEXT PRIMARY KEY,
            evals TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;
        """
    )
    for fen, evals in rows:
        conn.execute(
            "INSERT INTO cloud_eval (fen, evals) VALUES (?, ?)",
            (fen, json.dumps(evals)),
        )
    conn.execute(
        "INSERT INTO metadata (key, value) VALUES ('row_count', ?)",
        (str(len(rows)),),
    )
    conn.commit()
    conn.close()
    return db_path


# --- lookup ---


def test_lookup_hit(tmp_path: Path):
    """Returns API-compatible dict for a known position."""
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3"
    evals = [{"pvs": [{"cp": 30, "line": "e7e5 g1f3"}], "knodes": 1500, "depth": 54}]
    db_path = _make_test_db(tmp_path, [(fen, evals)])

    with patch("chess_self_coach.cloud_eval_db.find_cloud_eval_db", return_value=db_path):
        result = lookup_cloud_eval(fen)

    assert result is not None
    assert result["fen"] == fen
    assert result["depth"] == 54
    assert result["knodes"] == 1500
    assert len(result["pvs"]) == 1


def test_lookup_miss(tmp_path: Path):
    """Returns None for a position not in the DB."""
    db_path = _make_test_db(tmp_path, [])

    with patch("chess_self_coach.cloud_eval_db.find_cloud_eval_db", return_value=db_path):
        result = lookup_cloud_eval("8/8/8/8/8/8/8/8 w - -")

    assert result is None


def test_lookup_no_db():
    """Returns None when no DB is found."""
    with patch("chess_self_coach.cloud_eval_db.find_cloud_eval_db", return_value=None):
        result = lookup_cloud_eval("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -")

    assert result is None


def test_lookup_translates_line_to_moves(tmp_path: Path):
    """DB 'line' field is translated to API 'moves' field."""
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3"
    evals = [{"pvs": [{"cp": 30, "line": "e7e5 g1f3"}], "knodes": 1500, "depth": 54}]
    db_path = _make_test_db(tmp_path, [(fen, evals)])

    with patch("chess_self_coach.cloud_eval_db.find_cloud_eval_db", return_value=db_path):
        result = lookup_cloud_eval(fen)

    assert result is not None
    pv = result["pvs"][0]
    assert "moves" in pv
    assert "line" not in pv
    assert pv["moves"] == "e7e5 g1f3"


def test_lookup_selects_highest_depth(tmp_path: Path):
    """When multiple evals exist, selects the one with highest depth."""
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3"
    evals = [
        {"pvs": [{"cp": 30, "line": "e7e5"}], "knodes": 100, "depth": 40},
        {"pvs": [{"cp": 25, "line": "c7c5"}], "knodes": 200, "depth": 60},
        {"pvs": [{"cp": 28, "line": "e7e6"}], "knodes": 150, "depth": 50},
    ]
    db_path = _make_test_db(tmp_path, [(fen, evals)])

    with patch("chess_self_coach.cloud_eval_db.find_cloud_eval_db", return_value=db_path):
        result = lookup_cloud_eval(fen)

    assert result is not None
    assert result["depth"] == 60


def test_lookup_strips_fen_counters(tmp_path: Path):
    """6-field FEN query matches 4-field FEN in DB."""
    short_fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3"
    full_fen = short_fen + " 0 1"
    evals = [{"pvs": [{"cp": 30, "line": "e7e5"}], "knodes": 100, "depth": 54}]
    db_path = _make_test_db(tmp_path, [(short_fen, evals)])

    with patch("chess_self_coach.cloud_eval_db.find_cloud_eval_db", return_value=db_path):
        result = lookup_cloud_eval(full_fen)

    assert result is not None
    assert result["depth"] == 54


# --- cloud_eval_db_status ---


def test_status_found(tmp_path: Path):
    """Status reports correct info when DB exists."""
    db_path = _make_test_db(
        tmp_path,
        [("fen1 w KQkq -", [{"pvs": [], "depth": 50}])],
    )

    with patch("chess_self_coach.cloud_eval_db.find_cloud_eval_db", return_value=db_path):
        status = cloud_eval_db_status()

    assert status["found"] is True
    assert status["row_count"] == 1
    assert status["size_mb"] >= 0  # test DB is tiny, real DB is ~50 GB
    assert status["path"] == str(db_path)


def test_status_not_found():
    """Status reports not found when no DB exists."""
    with patch("chess_self_coach.cloud_eval_db.find_cloud_eval_db", return_value=None):
        status = cloud_eval_db_status()

    assert status["found"] is False
    assert status["row_count"] == 0


# --- Integration: query uses local DB ---


@patch("chess_self_coach.cloud_eval.requests.get")
@patch("chess_self_coach.cloud_eval_db.find_cloud_eval_db")
def test_query_uses_local_db(mock_find: MagicMock, mock_get: MagicMock, tmp_path: Path):
    """query_cloud_eval returns local DB result without calling the API."""
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3"
    evals = [{"pvs": [{"cp": 30, "line": "e7e5"}], "knodes": 100, "depth": 54}]
    db_path = _make_test_db(tmp_path, [(fen, evals)])
    mock_find.return_value = db_path

    from chess_self_coach.cloud_eval import query_cloud_eval

    result = query_cloud_eval(fen + " 0 1")

    assert result is not None
    assert result["depth"] == 54
    mock_get.assert_not_called()


@patch("chess_self_coach.cloud_eval_db.find_cloud_eval_db", return_value=None)
def test_query_falls_back_to_api(mock_find: MagicMock):
    """query_cloud_eval calls API when local DB returns None."""
    from chess_self_coach.cloud_eval import query_cloud_eval

    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("chess_self_coach.cloud_eval.requests.get", return_value=mock_resp):
        result = query_cloud_eval("8/8/8/8/8/8/8/8 w - - 0 1")

    assert result is None
