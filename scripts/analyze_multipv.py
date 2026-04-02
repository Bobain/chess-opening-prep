"""Enrich analysis_data.json with Stockfish MultiPV=3 data.

Adds a 'multipv_before' field to each non-opening move in analysis_data.json.
Emulates what the production pipeline will do: a single MultiPV=3 call per
position instead of separate single-PV + MultiPV passes.

Uses the same depth/time limits as the production pipeline (variable by piece count).
Skips Lichess API calls — keeps existing opening/cloud_eval/tablebase data.
Saves progress every N games so analysis can resume after interruption.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import chess
import chess.engine

PROJECT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT / "src"))

from chess_self_coach.analysis import (
    MULTIPV,
    AnalysisSettings,
    _analysis_limit_from_settings,
    _extract_multipv,
)

SF_PATH = "/usr/games/stockfish"
THREADS = 7
HASH_MB = 1024
SAVE_EVERY = 10  # save progress every N games

DATA_PATH = PROJECT / "data" / "analysis_data.json"


def analyze_position(
    engine: chess.engine.SimpleEngine,
    fen: str,
    limits: dict[str, dict[str, float | int]],
) -> dict:
    """Run MultiPV analysis with production depth limits.

    Uses the same functions as the production pipeline (analysis.py).

    Args:
        engine: Running Stockfish instance.
        fen: FEN string of the position to analyze.
        limits: Depth/time limits from AnalysisSettings.

    Returns:
        Compact dict: full PV1 line (best), derived features, alt first moves.
    """
    board = chess.Board(fen)
    limit = _analysis_limit_from_settings(board, limits)

    infos = engine.analyse(board, limit, multipv=MULTIPV)
    if not isinstance(infos, list):
        infos = [infos]

    return _extract_multipv(infos, board)


def main() -> None:
    """Enrich analysis_data.json with MultiPV data in-place."""
    print(f"Loading {DATA_PATH}...")
    with open(DATA_PATH) as f:
        data = json.load(f)

    games = data["games"]

    # Count work: only Stockfish positions need MultiPV enrichment
    todo = 0
    already_done = 0
    skipped = 0
    for game in games.values():
        for move in game["moves"]:
            if move.get("in_opening"):
                continue
            if move.get("eval_source") in ("cloud_eval", "tablebase"):
                skipped += 1
                continue
            if "multipv_before" in move:
                already_done += 1
            else:
                todo += 1

    total = todo + already_done
    print(f"Stockfish positions: {total} (skipped {skipped} cloud_eval/tablebase)")
    if already_done:
        print(f"Already enriched: {already_done} — resuming {todo} remaining")
    if todo == 0:
        print("Nothing to do.")
        return

    settings = AnalysisSettings(threads=THREADS, hash_mb=HASH_MB)
    limits = settings.limits

    print(f"MultiPV={MULTIPV}, production depth limits: {limits}")
    print(f"Engine: {SF_PATH}, threads={THREADS}, hash={HASH_MB}MB")
    print("Engine restarted between games (clean hash table)")

    done = 0
    games_since_save = 0
    t0 = time.time()
    engine: chess.engine.SimpleEngine | None = None

    for url, game in games.items():
        # Skip fully enriched games
        needs_work = any(
            "multipv_before" not in m
            for m in game["moves"]
            if not m.get("in_opening")
        )
        if not needs_work:
            continue

        # Fresh engine per game — clean hash table, no cross-game pollution
        if engine is not None:
            engine.quit()
        engine = chess.engine.SimpleEngine.popen_uci(SF_PATH)
        engine.configure({"Threads": THREADS, "Hash": HASH_MB})

        for move in game["moves"]:
            if move.get("in_opening"):
                continue
            if "multipv_before" in move:
                continue  # already enriched
            # Skip non-Stockfish positions (production doesn't MultiPV these)
            if move.get("eval_source") in ("cloud_eval", "tablebase"):
                continue

            fen = move["fen_before"]
            try:
                mpv = analyze_position(engine, fen, limits)
                move["multipv_before"] = mpv
            except Exception as e:
                print(f"  Error on {url} fen={fen[:30]}...: {e}")
                move["multipv_before"] = None

            done += 1
            if done % 100 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (todo - done) / rate
                print(
                    f"  [{already_done + done}/{total}] "
                    f"{rate:.1f} pos/s, ETA {eta / 60:.0f}min"
                )

        games_since_save += 1

        # Incremental save
        if games_since_save >= SAVE_EVERY:
            _save(data)
            games_since_save = 0

    if engine is not None:
        engine.quit()

    # Final save
    _save(data)

    elapsed = time.time() - t0
    print(f"\nDone: {done} positions in {elapsed:.0f}s ({done / elapsed:.1f} pos/s)")


def _save(data: dict) -> None:
    """Save analysis_data.json atomically."""
    tmp = DATA_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    tmp.replace(DATA_PATH)
    print(f"  [saved to {DATA_PATH.name}]")


if __name__ == "__main__":
    main()
