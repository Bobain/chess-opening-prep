"""Tests for opening_explorer.py — API client and theory departure detection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from chess_self_coach.opening_explorer import (
    ExplorerAPIError,
    query_opening,
    query_opening_sequence,
)


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    return resp


# --- query_opening ---


@patch("chess_self_coach.opening_explorer.requests.get")
def test_query_opening_returns_data(mock_get: MagicMock):
    """Successful query returns the full response."""
    api_data = {
        "opening": {"eco": "B00", "name": "King's Pawn Game"},
        "white": 100, "draws": 50, "black": 80,
        "moves": [
            {"san": "e5", "uci": "e7e5", "white": 40, "draws": 20, "black": 30},
        ],
    }
    mock_get.return_value = _mock_response(api_data)

    result = query_opening("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1", "token")
    assert result is not None
    assert result["opening"]["eco"] == "B00"
    assert len(result["moves"]) == 1


@patch("chess_self_coach.opening_explorer.requests.get")
def test_query_opening_zero_games_returns_none(mock_get: MagicMock):
    """Position with zero games is treated as not in database."""
    api_data = {"opening": None, "white": 0, "draws": 0, "black": 0, "moves": []}
    mock_get.return_value = _mock_response(api_data)

    result = query_opening("some/fen", "token")
    assert result is None


@patch("chess_self_coach.opening_explorer.requests.get")
def test_query_opening_api_error_raises(mock_get: MagicMock):
    """API error raises ExplorerAPIError (never silently returns None)."""
    mock_get.return_value = _mock_response({}, status_code=500)

    with pytest.raises(ExplorerAPIError, match="API unavailable"):
        query_opening("some/fen", "token")


@patch("chess_self_coach.opening_explorer.requests.get")
def test_query_opening_network_error_raises(mock_get: MagicMock):
    """Network error raises ExplorerAPIError (never silently returns None)."""
    import requests

    mock_get.side_effect = requests.ConnectionError("timeout")

    with pytest.raises(ExplorerAPIError, match="API unavailable"):
        query_opening("some/fen", "token")


# --- query_opening_sequence ---


@patch("chess_self_coach.opening_explorer.query_opening")
@patch("chess_self_coach.opening_explorer.time.sleep")
def test_sequence_stops_at_departure(mock_sleep: MagicMock, mock_query: MagicMock):
    """Stops querying after Masters departs."""
    masters_resp1 = {
        "opening": {"eco": "B00", "name": "King's Pawn"},
        "white": 100, "draws": 50, "black": 80,
        "moves": [{"uci": "e7e5", "san": "e5"}],
    }
    # Position 2: Masters has d4 but NOT Nf6 → masters departure
    masters_resp2 = {
        "opening": {"eco": "C20", "name": "King's Pawn Game"},
        "white": 50, "draws": 20, "black": 30,
        "moves": [{"uci": "d2d4", "san": "d4"}],
    }

    mock_query.side_effect = [masters_resp1, masters_resp2]

    fens_and_moves = [
        ("startpos_fen", "e7e5"),
        ("after_e5_fen", "g8f6"),  # Nf6 not in Masters → departure
        ("after_nf6_fen", "d2d4"),  # Should not be queried
    ]

    results = query_opening_sequence(fens_and_moves, "token")
    assert len(results) == 3
    assert results[0] is not None
    assert results[0]["_source"] == "masters"
    assert results[1] is None  # Masters departed
    assert results[2] is None  # Past departure: not queried
    assert mock_query.call_count == 2


@patch("chess_self_coach.opening_explorer.query_opening")
@patch("chess_self_coach.opening_explorer.time.sleep")
def test_sequence_preserves_existing_masters(mock_sleep: MagicMock, mock_query: MagicMock):
    """Re-analysis preserves existing masters data and re-tests at breakpoint."""
    # Existing data: masters for ply 0, nothing for ply 1+
    existing = [
        {"_source": "masters", "opening": {"eco": "B00"}, "moves": [{"uci": "e7e5"}]},
        None,  # ply 1 had no masters data
    ]

    # At ply 1 (breakpoint), masters now has the move → extension
    new_masters_resp = {
        "opening": {"eco": "C20"}, "white": 50, "draws": 20, "black": 30,
        "moves": [{"uci": "d7d5", "san": "d5"}],
    }

    mock_query.side_effect = [new_masters_resp]

    fens_and_moves = [
        ("fen1", "e7e5"),  # Existing masters → preserved, no API call
        ("fen2", "d7d5"),  # No existing → query masters → found!
    ]

    results = query_opening_sequence(fens_and_moves, "token", existing_results=existing)
    assert results[0]["_source"] == "masters"  # Preserved
    assert results[0] is existing[0]  # Same object, not re-fetched
    assert results[1] is not None
    assert results[1]["_source"] == "masters"  # Extended!
    assert mock_query.call_count == 1  # Only queried at breakpoint


@patch("chess_self_coach.opening_explorer.query_opening")
@patch("chess_self_coach.opening_explorer.time.sleep")
def test_sequence_stops_when_masters_returns_none(mock_sleep: MagicMock, mock_query: MagicMock):
    """Stops querying when Masters returns None (position not in database)."""
    mock_query.side_effect = [
        # Pos1 Masters: has e7e5
        {"opening": None, "white": 100, "draws": 50, "black": 80, "moves": [{"uci": "e7e5"}]},
        # Pos2 Masters: None (not in database) → departure
        None,
    ]

    fens_and_moves = [
        ("fen1", "e7e5"),
        ("fen2", "d7d5"),
        ("fen3", "g1f3"),
    ]

    results = query_opening_sequence(fens_and_moves, "token")
    assert results[0] is not None
    assert results[1] is None
    assert results[2] is None
    assert mock_query.call_count == 2  # Masters x2, then departed
