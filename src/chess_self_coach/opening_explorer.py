"""Lichess Masters Opening Explorer API client.

Queries the Lichess Masters opening explorer (FIDE 2200+ OTB games) to identify
opening names, ECO codes, and move popularity statistics for each position.
Used during Phase 1 analysis to detect when players depart from known theory.

A move is considered "in opening" (in_opening=True) only if it appears in the
Masters database.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

from chess_self_coach.config import analysis_data_path
from chess_self_coach.io import atomic_write_json

_log = logging.getLogger(__name__)

# Masters endpoint: FIDE 2200+ OTB games (real opening theory)
_MASTERS_PRIMARY = "https://explorer.lichess.ovh/masters"
_MASTERS_FALLBACK = "https://explorer.lichess.org/masters"

# Request timeout (seconds)
_TIMEOUT = 10.0

# Delay between requests to respect rate limits (seconds)
_RATE_LIMIT_DELAY = 0.1


class ExplorerAPIError(Exception):
    """Raised when the Opening Explorer API is unavailable or rate-limited."""


def _query_endpoint(
    fen: str,
    token: str,
    primary_url: str,
    fallback_url: str,
    params: dict[str, str],
) -> dict | None:
    """Query a single Opening Explorer endpoint.

    Returns:
        The full API response dict, or None if the position has zero games
        (legitimate "not in database").

    Raises:
        ExplorerAPIError: If both endpoints fail (network error, rate limit,
            server error). Never silently returns None for API failures.
    """
    headers = {"Authorization": f"Bearer {token}"}
    last_error: str | None = None

    for url in (primary_url, fallback_url):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                total = data.get("white", 0) + data.get("draws", 0) + data.get("black", 0)
                if total == 0:
                    return None
                return data
            if resp.status_code == 429:
                time.sleep(1.0)
                resp = requests.get(url, params=params, headers=headers, timeout=_TIMEOUT)
                if resp.status_code == 200:
                    data = resp.json()
                    total = data.get("white", 0) + data.get("draws", 0) + data.get("black", 0)
                    if total == 0:
                        return None
                    return data
                last_error = f"Rate limited (429) on {url}, retry also failed ({resp.status_code})"
            else:
                last_error = f"HTTP {resp.status_code} from {url}"
        except requests.RequestException as exc:
            last_error = f"Network error on {url}: {exc}"
            continue

    raise ExplorerAPIError(
        f"Opening Explorer API unavailable: {last_error}. "
        f"Check your network connection and Lichess API token."
    )


def query_opening(fen: str, token: str) -> dict | None:
    """Query the Lichess Masters Opening Explorer for a position.

    Args:
        fen: FEN string of the position to query.
        token: Lichess API personal access token.

    Returns:
        Dict with {opening, white, draws, black, moves[]} or None if position
        has zero games in Masters database.

    Raises:
        ExplorerAPIError: If both primary/fallback endpoints fail.
    """
    return _query_endpoint(fen, token, _MASTERS_PRIMARY, _MASTERS_FALLBACK, {"fen": fen})


def query_opening_sequence(
    fens_and_moves: list[tuple[str, str]],
    token: str,
    *,
    existing_results: list[dict | None] | None = None,
) -> list[dict | None]:
    """Query the Masters Opening Explorer for a sequence of positions.

    Queries Masters until the played move is not found (theory departure).
    Each returned dict has ``_source="masters"``.

    When *existing_results* is provided (re-analysis), positions that already
    have Masters data are preserved without API calls.  Querying resumes from
    the first position without Masters data (breakpoint re-testing).

    Args:
        fens_and_moves: List of (fen_before, move_uci) tuples for each ply.
        token: Lichess API personal access token.
        existing_results: Previous opening_explorer data per ply (from a prior
            analysis).  Entries with ``_source="masters"`` are kept as-is.

    Returns:
        List of explorer responses (same length as input). None entries mean
        the position was past theory departure.
    """
    results: list[dict | None] = []
    masters_departed = False

    for i, (fen, move_uci) in enumerate(fens_and_moves):
        # Re-analysis: preserve existing masters data
        if (
            not masters_departed
            and existing_results is not None
            and i < len(existing_results)
        ):
            existing = existing_results[i]
            if existing is not None and existing.get("_source") == "masters":
                results.append(existing)
                continue
            # No existing masters data → fall through to query

        if masters_departed:
            results.append(None)
            continue

        md = query_opening(fen, token)
        if md is not None:
            known = {m["uci"] for m in md.get("moves", [])}
            if move_uci in known:
                md["_source"] = "masters"
                results.append(md)
            else:
                masters_departed = True
                results.append(None)
        else:
            masters_departed = True
            results.append(None)

        time.sleep(_RATE_LIMIT_DELAY)

    return results


def refresh_opening_data(
    path: Path | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Re-query Masters for existing games to update in_opening flags.

    For each game, iterates through moves that currently have in_opening=True.
    Queries Masters for each position until Masters departs, then sets
    in_opening=False for that move and all subsequent moves.

    Does NOT re-run Stockfish or touch eval data.

    Args:
        path: Path to analysis_data.json. Defaults to config.
        token: Lichess API token. Required for API calls.

    Returns:
        Dict with stats: {games_updated, moves_changed, total_masters}.
    """
    if path is None:
        path = analysis_data_path()

    with open(path) as f:
        data = json.load(f)

    games = data.get("games", {})
    stats = {"games_updated": 0, "moves_changed": 0, "total_masters": 0}

    try:
        for i, (game_id, game_data) in enumerate(games.items()):
            moves = game_data.get("moves", [])
            masters_departed = False
            game_changed = False

            for move in moves:
                old_in_opening = move.get("in_opening", False)

                if masters_departed:
                    # After Masters departure: force in_opening=False
                    if old_in_opening:
                        move["in_opening"] = False
                        game_changed = True
                        stats["moves_changed"] += 1
                    continue

                if not old_in_opening:
                    # Already out of opening — stop checking this game
                    break

                # Was in_opening=True: check Masters
                fen = move.get("fen_before")
                move_uci = move.get("move_uci")
                if not fen or not move_uci or not token:
                    masters_departed = True
                    move["in_opening"] = False
                    game_changed = True
                    stats["moves_changed"] += 1
                    continue

                # ExplorerAPIError propagates — never silently treat API
                # failure as "not in theory"
                md = query_opening(fen, token)
                if md is not None:
                    known = {m["uci"] for m in md.get("moves", [])}
                    if move_uci in known:
                        # Masters confirms this move — update explorer data
                        md["_source"] = "masters"
                        move["opening_explorer"] = md
                        stats["total_masters"] += 1
                    else:
                        # Move not in Masters — departure
                        masters_departed = True
                        move["in_opening"] = False
                        game_changed = True
                        stats["moves_changed"] += 1
                else:
                    # Position not in Masters (0 games) — departure
                    masters_departed = True
                    move["in_opening"] = False
                    game_changed = True
                    stats["moves_changed"] += 1

                time.sleep(_RATE_LIMIT_DELAY)

            if game_changed:
                stats["games_updated"] += 1

            if (i + 1) % 50 == 0 or i + 1 == len(games):
                print(f"  Refreshed {i + 1}/{len(games)} games...")

    except ExplorerAPIError as exc:
        print(f"\n  ERROR: API failure — {exc}")
        print(f"  Saving partial progress ({stats['games_updated']} games updated so far)...")
        atomic_write_json(path, data)
        raise

    atomic_write_json(path, data)
    print(f"  Done: {stats['games_updated']} games updated, "
          f"{stats['moves_changed']} moves changed, "
          f"{stats['total_masters']} moves confirmed in Masters")
    return stats
