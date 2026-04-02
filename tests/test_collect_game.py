"""Tests for collect_game_data() — Phase 1 per-game data collection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import chess
import chess.engine
import chess.pgn

from chess_self_coach.analysis import (
    AnalysisSettings,
    _analysis_limit_from_settings,
    _extract_eval,
    _extract_multipv,
    _score_to_cp,
    _tb_to_eval,
    collect_game_data,
)

MINI_PGN = Path(__file__).parent / "fixtures" / "mini.pgn"


# --- _score_to_cp ---


def test_score_to_cp_positive():
    """Positive centipawn score from White's perspective."""
    score = chess.engine.PovScore(chess.engine.Cp(50), chess.WHITE)
    cp, is_mate, mate_in = _score_to_cp(score)
    assert cp == 50
    assert not is_mate
    assert mate_in is None


def test_score_to_cp_mate():
    """Mate score returns sentinel value and mate distance."""
    score = chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE)
    cp, is_mate, mate_in = _score_to_cp(score)
    assert cp == 10000
    assert is_mate
    assert mate_in == 3


def test_score_to_cp_mated():
    """Being mated returns negative sentinel."""
    score = chess.engine.PovScore(chess.engine.Mate(-2), chess.WHITE)
    cp, is_mate, mate_in = _score_to_cp(score)
    assert cp == -10000
    assert is_mate
    assert mate_in == -2


def test_score_to_cp_black_perspective():
    """Score from Black's perspective is flipped to White's."""
    score = chess.engine.PovScore(chess.engine.Cp(-30), chess.BLACK)
    cp, is_mate, mate_in = _score_to_cp(score)
    assert cp == 30  # Black has -30 = White has +30


# --- _analysis_limit_from_settings ---


def test_limit_default_depth():
    """Default bracket uses depth from settings."""
    board = chess.Board()  # Starting position (32 pieces)
    limits = {"default": {"depth": 22}}
    limit = _analysis_limit_from_settings(board, limits)
    assert limit.depth == 22


def test_limit_endgame():
    """Endgame bracket uses time+depth."""
    board = chess.Board("4k3/8/8/8/8/8/8/4K2R w K - 0 1")  # 3 pieces
    limits = {"pieces_le7": {"time": 5.0, "depth": 50}, "default": {"depth": 18}}
    limit = _analysis_limit_from_settings(board, limits)
    assert limit.depth == 50
    assert limit.time == 5.0


def test_limit_kings_pawns():
    """King+pawns bracket takes priority over pieces_le7."""
    board = chess.Board("4k3/p7/8/8/8/8/P7/4K3 w - - 0 1")  # 4 pieces, K+P only
    limits = {
        "kings_pawns_le7": {"time": 6.0, "depth": 60},
        "pieces_le7": {"time": 5.0, "depth": 50},
        "default": {"depth": 18},
    }
    limit = _analysis_limit_from_settings(board, limits)
    assert limit.depth == 60
    assert limit.time == 6.0


# --- _extract_eval ---


def test_extract_eval_with_score():
    """Extracts full eval from a Stockfish info dict."""
    board = chess.Board()
    pv_moves = [chess.Move.from_uci("e2e4"), chess.Move.from_uci("e7e5")]
    info = {
        "score": chess.engine.PovScore(chess.engine.Cp(30), chess.WHITE),
        "pv": pv_moves,
        "depth": 18,
        "seldepth": 24,
        "nodes": 1500000,
        "nps": 1200000,
        "time": 1.25,
        "tbhits": 0,
        "hashfull": 42,
    }
    result = _extract_eval(info, board)
    assert result["score_cp"] == 30
    assert not result["is_mate"]
    assert result["depth"] == 18
    assert result["seldepth"] == 24
    assert result["nodes"] == 1500000
    assert result["time_ms"] == 1250
    assert result["pv_san"] == ["e4", "e5"]
    assert result["pv_uci"] == ["e2e4", "e7e5"]
    assert result["best_move_san"] == "e4"
    assert result["best_move_uci"] == "e2e4"


def test_extract_eval_no_score():
    """Missing score returns null fields."""
    board = chess.Board()
    info = {}
    result = _extract_eval(info, board)
    assert result["score_cp"] is None
    assert result["pv_san"] == []


# --- _extract_multipv ---


def test_extract_multipv_basic():
    """MultiPV with 3 lines produces correct move_gap, n_good_moves, alt."""
    board = chess.Board()
    moves = list(board.legal_moves)
    infos = [
        {"score": chess.engine.PovScore(chess.engine.Cp(50), chess.WHITE), "pv": [moves[0]]},
        {"score": chess.engine.PovScore(chess.engine.Cp(20), chess.WHITE), "pv": [moves[1]]},
        {"score": chess.engine.PovScore(chess.engine.Cp(-40), chess.WHITE), "pv": [moves[2]]},
    ]
    result = _extract_multipv(infos, board)
    assert result["move_gap"] == 30  # 50 - 20
    assert result["n_good_moves"] == 2  # 50 and 20 are within 50cp of 50
    assert len(result["alt"]) == 2
    assert result["alt"][0]["cp"] == 20
    assert result["alt"][1]["cp"] == -40


def test_extract_multipv_empty():
    """Empty info list returns neutral defaults."""
    board = chess.Board()
    result = _extract_multipv([], board)
    assert result["move_gap"] is None
    assert result["n_good_moves"] == 0
    assert result["alt"] == []


# --- _tb_to_eval ---


def test_tb_to_eval_win_white():
    """Tablebase WIN for White produces positive score."""
    tb_data = {
        "tier": "WIN",
        "dtm": 15,
        "moves": [{"san": "Rh7", "uci": "h1h7"}],
    }
    result = _tb_to_eval(tb_data, chess.WHITE)
    assert result["score_cp"] == 10000
    assert result["best_move_san"] == "Rh7"


def test_tb_to_eval_loss_black():
    """Tablebase LOSS for Black (side to move) flips perspective."""
    tb_data = {"tier": "LOSS", "dtm": -10, "moves": []}
    result = _tb_to_eval(tb_data, chess.BLACK)
    assert result["score_cp"] == 10000  # LOSS for Black = WIN for White


# --- collect_game_data ---


def _make_mock_engine() -> MagicMock:
    """Create a mock Stockfish engine that returns deterministic results.

    When called with multipv=N, returns a list of N InfoDicts with decreasing
    scores (simulating PV1 > PV2 > PV3). Without multipv, returns a single dict.
    """
    engine = MagicMock(spec=chess.engine.SimpleEngine)
    call_count = {"n": 0}

    def mock_analyse(board: chess.Board, limit: chess.engine.Limit, **kwargs):
        call_count["n"] += 1
        multipv = kwargs.get("multipv", 1)
        legal = list(board.legal_moves)
        # Return a simple eval that varies by position
        score_val = 20 + call_count["n"]

        def _make_info(idx: int) -> dict:
            pv_moves = legal[idx : idx + 2] if idx < len(legal) else []
            return {
                "score": chess.engine.PovScore(
                    chess.engine.Cp(score_val - idx * 30), chess.WHITE
                ),
                "pv": pv_moves,
                "depth": 5,
                "seldepth": 8,
                "nodes": 10000,
                "nps": 100000,
                "time": 0.1,
                "tbhits": 0,
                "hashfull": 10,
            }

        if multipv > 1:
            return [_make_info(i) for i in range(min(multipv, len(legal)))]
        return _make_info(0)

    engine.analyse = mock_analyse
    return engine


@patch("chess_self_coach.analysis.probe_position_full", return_value=None)
def test_collect_game_data_move_count(mock_tb: MagicMock):
    """Collects correct number of moves from mini.pgn (5 half-moves)."""
    game = chess.pgn.read_game(open(MINI_PGN))
    engine = _make_mock_engine()
    settings = AnalysisSettings(threads=1, hash_mb=64, limits={"default": {"depth": 5}})

    result = collect_game_data(game, engine, chess.WHITE, settings, lichess_token=None)
    assert len(result["moves"]) == 5
    assert result["player_color"] == "white"


@patch("chess_self_coach.analysis.probe_position_full", return_value=None)
def test_collect_game_data_field_presence(mock_tb: MagicMock):
    """Each move has all required fields."""
    game = chess.pgn.read_game(open(MINI_PGN))
    engine = _make_mock_engine()
    settings = AnalysisSettings(threads=1, hash_mb=64, limits={"default": {"depth": 5}})

    result = collect_game_data(game, engine, chess.WHITE, settings)
    move = result["moves"][0]

    required_fields = [
        "ply", "fen_before", "fen_after", "move_san", "move_uci", "side",
        "eval_source", "eval_before", "eval_after", "multipv_before",
        "tablebase_before", "tablebase_after", "opening_explorer",
        "cp_loss", "board", "clock",
    ]
    for field in required_fields:
        assert field in move, f"Missing field: {field}"

    # Check nested structures
    assert "score_cp" in move["eval_before"]
    assert "pv_san" in move["eval_before"]
    assert "piece_count" in move["board"]
    assert "is_check" in move["board"]

    # MultiPV: for Stockfish-evaluated moves, multipv_before has expected keys
    # (may be None for cloud-eval/tablebase moves, which lack multiPV)
    sf_moves = [m for m in result["moves"] if m["eval_source"] == "stockfish"]
    if sf_moves:
        mpv = sf_moves[0]["multipv_before"]
        assert mpv is not None, "multipv_before should not be None for Stockfish moves"
        assert "move_gap" in mpv
        assert "n_good_moves" in mpv
        assert "alt" in mpv


@patch("chess_self_coach.analysis.probe_position_full", return_value=None)
def test_collect_game_data_ply_sequence(mock_tb: MagicMock):
    """Ply numbers are sequential 1..N."""
    game = chess.pgn.read_game(open(MINI_PGN))
    engine = _make_mock_engine()
    settings = AnalysisSettings(threads=1, hash_mb=64, limits={"default": {"depth": 5}})

    result = collect_game_data(game, engine, chess.WHITE, settings)
    plies = [m["ply"] for m in result["moves"]]
    assert plies == [1, 2, 3, 4, 5]


@patch("chess_self_coach.analysis.probe_position_full", return_value=None)
def test_collect_game_data_alternating_sides(mock_tb: MagicMock):
    """Sides alternate white/black."""
    game = chess.pgn.read_game(open(MINI_PGN))
    engine = _make_mock_engine()
    settings = AnalysisSettings(threads=1, hash_mb=64, limits={"default": {"depth": 5}})

    result = collect_game_data(game, engine, chess.WHITE, settings)
    sides = [m["side"] for m in result["moves"]]
    assert sides == ["white", "black", "white", "black", "white"]


@patch("chess_self_coach.analysis.probe_position_full", return_value=None)
def test_collect_game_data_headers(mock_tb: MagicMock):
    """Game headers are extracted correctly."""
    game = chess.pgn.read_game(open(MINI_PGN))
    engine = _make_mock_engine()
    settings = AnalysisSettings(threads=1, hash_mb=64, limits={"default": {"depth": 5}})

    result = collect_game_data(game, engine, chess.WHITE, settings)
    assert result["headers"]["white"] == "White"
    assert result["headers"]["black"] == "Black"
    assert "analyzed_at" in result
    assert "settings" in result


@patch("chess_self_coach.analysis.query_cloud_eval", return_value=None)
@patch("chess_self_coach.analysis.probe_position_full", return_value=None)
def test_collect_game_data_multipv_present(mock_tb: MagicMock, mock_cloud: MagicMock):
    """All moves have multipv_before when only Stockfish is used (no cloud/tb)."""
    game = chess.pgn.read_game(open(MINI_PGN))
    engine = _make_mock_engine()
    settings = AnalysisSettings(threads=1, hash_mb=64, limits={"default": {"depth": 5}})

    result = collect_game_data(game, engine, chess.WHITE, settings)
    for move in result["moves"]:
        mpv = move["multipv_before"]
        assert mpv is not None, f"ply {move['ply']}: multipv_before is None"
        assert "move_gap" in mpv
        assert "n_good_moves" in mpv
        assert isinstance(mpv["alt"], list)
