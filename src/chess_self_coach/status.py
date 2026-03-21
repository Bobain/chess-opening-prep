"""Status overview of the chess opening repertoire.

Shows local file status, Stockfish availability, and Lichess study configuration.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import chess.pgn

from chess_self_coach.config import (
    _find_project_root,
    check_stockfish_version,
    find_stockfish,
    load_config,
)


def _count_chapters(pgn_path: Path) -> int:
    """Count the number of games (chapters) in a PGN file.

    Args:
        pgn_path: Path to the PGN file.

    Returns:
        Number of games found.
    """
    count = 0
    try:
        with open(pgn_path) as f:
            while chess.pgn.read_game(f) is not None:
                count += 1
    except Exception as exc:
        print(f"  Warning: could not read {pgn_path}: {exc}", file=sys.stderr)
    return count


def _format_timestamp(path: Path) -> str:
    """Format the last modification time of a file.

    Args:
        path: Path to the file.

    Returns:
        Human-readable timestamp or "missing".
    """
    if not path.exists():
        return "missing"
    mtime = os.path.getmtime(path)
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


def get_status_data(project_root: Path) -> dict:
    """Compute status overview of the repertoire setup.

    Args:
        project_root: Path to the project root.

    Returns:
        Dict with keys: config_ok, stockfish, has_token, files, suggestions.
    """
    import json

    pgn_dir = project_root / "pgn"

    # Load config directly (avoids _find_project_root coupling)
    config_path = project_root / "config.json"
    if not config_path.exists():
        return {
            "config_ok": False,
            "stockfish": {"available": False, "version": ""},
            "has_token": False,
            "files": [],
            "suggestions": ["Run 'chess-self-coach setup' to create config.json"],
        }

    with open(config_path) as f:
        config = json.load(f)

    # Stockfish check
    try:
        sf_path = find_stockfish(config)
        expected = config.get("stockfish", {}).get("expected_version")
        version = check_stockfish_version(sf_path, expected)
        stockfish = {"available": True, "version": version}
    except SystemExit:
        stockfish = {"available": False, "version": ""}

    # Lichess token check
    token = os.environ.get("LICHESS_API_TOKEN", "")
    if not token:
        from dotenv import load_dotenv

        env_path = project_root / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            token = os.environ.get("LICHESS_API_TOKEN", "")
    has_token = bool(token)

    # PGN files status
    files = []
    studies = config.get("studies", {})
    for pgn_file, study_info in studies.items():
        pgn_path = pgn_dir / pgn_file
        study_id = study_info.get("study_id", "")
        files.append({
            "file": pgn_file,
            "modified": _format_timestamp(pgn_path),
            "chapters": _count_chapters(pgn_path) if pgn_path.exists() else 0,
            "study_configured": not study_id.startswith("STUDY_ID"),
        })

    # Suggestions
    suggestions = []
    if not has_token:
        suggestions.append("Create a Lichess token: chess-self-coach setup")
    for pgn_file, study_info in studies.items():
        study_id = study_info.get("study_id", "")
        if study_id.startswith("STUDY_ID"):
            suggestions.append(f"Configure study for {pgn_file}: chess-self-coach setup")
            break
    for pgn_file in studies:
        pgn_path = pgn_dir / pgn_file
        if pgn_path.exists():
            with open(pgn_path) as f:
                content = f.read()
            if "[%eval" not in content:
                suggestions.append(f"Analyze {pgn_file}: chess-self-coach analyze pgn/{pgn_file}")

    return {
        "config_ok": True,
        "stockfish": stockfish,
        "has_token": has_token,
        "files": files,
        "suggestions": suggestions,
    }


def show_status() -> None:
    """Display the current status of all repertoire files and integrations."""
    print("\n📊 chess-self-coach status\n")

    root = _find_project_root()
    data = get_status_data(root)

    if not data["config_ok"]:
        print("  ❌ config.json not found. Run 'chess-self-coach setup' first.\n")
        return

    # Stockfish
    print("Stockfish:")
    sf = data["stockfish"]
    if sf["available"]:
        print(f"  ✓ {sf['version']}")
    else:
        print("  ❌ Not found (run 'chess-self-coach setup')")

    # Token
    print("\nLichess token:")
    if data["has_token"]:
        print("  ✓ Configured")
    else:
        print("  ❌ Not configured (see .env.example)")

    # PGN files
    print("\nPGN files:")
    header = f"  {'File':<50} {'Modified':<18} {'Chapters':>8}  {'Study'}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for f in data["files"]:
        study_display = "✓ configured" if f["study_configured"] else "⚠ NOT CONFIGURED"
        print(f"  {f['file']:<50} {f['modified']:<18} {f['chapters']:>8}  {study_display}")

    # Suggestions
    print("\nSuggested actions:")
    if data["suggestions"]:
        for s in data["suggestions"]:
            print(f"  - {s}")
    else:
        print("  ✓ Everything looks good!")

    print()
