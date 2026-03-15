"""Lichess Study integration — setup, push, and pull subcommands.

Uses the berserk library (official Lichess Python client) to import/export
PGN content to/from Lichess Studies.
"""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path

import berserk

from chess_opening_prep.config import (
    error_exit,
    load_config,
    load_lichess_token,
    save_config,
    _find_project_root,
)


def _get_client() -> berserk.Client:
    """Create an authenticated berserk client.

    Returns:
        Authenticated berserk Client.

    Raises:
        SystemExit: If auth fails.
    """
    token = load_lichess_token()
    session = berserk.TokenSession(token)
    client = berserk.Client(session=session)

    # Verify auth
    try:
        account = client.account.get()
        username = account.get("username", "unknown")
        print(f"  Authenticated as: {username}")
        return client
    except berserk.exceptions.ResponseError as e:
        error_exit(
            f"Lichess authentication failed: {e}",
            hint="Your token may be invalid or expired.\n"
            "  Regenerate at: https://lichess.org/account/oauth/token/create",
            debug_cmd=(
                "curl -s -H 'Authorization: Bearer $LICHESS_API_TOKEN' "
                "https://lichess.org/api/account | python3 -m json.tool"
            ),
        )
    return None  # unreachable


def setup() -> None:
    """Interactive setup: verify auth, find studies, configure config.json.

    Guides the user through connecting their Lichess account and mapping
    PGN files to Lichess Studies.
    """
    print("\n🔧 chess-opening-prep setup\n")

    # Step 1: Verify auth
    print("Step 1: Checking Lichess authentication...")
    client = _get_client()

    # Step 2: Check Stockfish
    print("\nStep 2: Checking Stockfish...")
    from chess_opening_prep.config import find_stockfish, check_stockfish_version

    try:
        config = load_config()
    except SystemExit:
        config = {
            "stockfish": {
                "path": str(
                    Path.home()
                    / ".local/share/org.encroissant.app/engines/stockfish"
                    / "stockfish-ubuntu-x86-64-avx2"
                ),
                "expected_version": "Stockfish 18",
                "fallback_path": "/usr/games/stockfish",
            },
            "analysis": {"default_depth": 18, "blunder_threshold": 1.0},
            "studies": {},
        }

    sf_path = find_stockfish(config)
    version = check_stockfish_version(sf_path, config.get("stockfish", {}).get("expected_version"))
    print(f"  Found {version} at {sf_path}")

    # Step 3: List user's studies and try to match
    print("\nStep 3: Looking for existing Lichess studies...")
    account = client.account.get()
    username = account["username"]

    try:
        studies = list(client.studies.get_by_user(username))
    except Exception:
        studies = []

    # Expected study names and their PGN files
    expected_studies = {
        "repertoire_blancs_gambit_dame_annote.pgn": "Whites - Queen's Gambit",
        "repertoire_noirs_vs_e4_scandinave_annote.pgn": "Black vs e4 - Scandinavian",
        "repertoire_noirs_vs_d4_slave_annote.pgn": "Black vs d4 - Slav",
    }

    studies_config = config.get("studies", {})

    if studies:
        print(f"  Found {len(studies)} study/studies on your account:")
        for study in studies:
            study_name = study.get("name", "Unnamed")
            study_id = study.get("id", "???")
            print(f"    - {study_name} (id: {study_id})")

        # Try to auto-match by name
        for pgn_file, expected_name in expected_studies.items():
            if pgn_file in studies_config and not studies_config[pgn_file].get(
                "study_id", ""
            ).startswith("STUDY_ID"):
                print(f"  ✓ {pgn_file} already configured")
                continue

            matched = None
            for study in studies:
                study_name = study.get("name", "")
                if expected_name.lower() in study_name.lower():
                    matched = study
                    break

            if matched:
                studies_config[pgn_file] = {
                    "study_id": matched["id"],
                    "study_name": matched["name"],
                }
                print(f"  ✓ Auto-matched {pgn_file} → {matched['name']} ({matched['id']})")
            else:
                studies_config[pgn_file] = {
                    "study_id": "STUDY_ID_HERE",
                    "study_name": expected_name,
                }
                print(f"  ✗ No match for {pgn_file} (expected: '{expected_name}')")
    else:
        print("  No studies found on your account.")
        for pgn_file, expected_name in expected_studies.items():
            studies_config[pgn_file] = {
                "study_id": "STUDY_ID_HERE",
                "study_name": expected_name,
            }

    config["studies"] = studies_config
    save_config(config)

    # Check if any studies still need to be created
    missing = [
        (pgn, info["study_name"])
        for pgn, info in studies_config.items()
        if info.get("study_id", "").startswith("STUDY_ID")
    ]

    if missing:
        print(f"\n  {len(missing)} study/studies need to be created on Lichess:")
        for pgn, name in missing:
            print(f"    - {name} (for {pgn})")
        print("\n  Opening Lichess study page in your browser...")
        try:
            webbrowser.open("https://lichess.org/study")
        except Exception:
            print("  Could not open browser. Go to: https://lichess.org/study")
        print(
            "\n  After creating the studies, run 'chess-opening-prep setup' again\n"
            "  to auto-detect them, or edit config.json manually."
        )
    else:
        print("\n  ✓ All studies configured!")

    print("\n✓ Setup complete.\n")


def push_pgn(pgn_path: str | Path, *, replace: bool = False) -> None:
    """Push a local PGN file to its mapped Lichess study.

    Args:
        pgn_path: Path to the PGN file.
        replace: If True, warn about chapter duplication.
    """
    pgn_path = Path(pgn_path)
    if not pgn_path.exists():
        print(f"❌ File not found: {pgn_path}", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    from chess_opening_prep.config import get_study_mapping

    mapping = get_study_mapping(config, pgn_path.name)
    study_id = mapping["study_id"]
    study_name = mapping.get("study_name", study_id)

    client = _get_client()

    pgn_content = pgn_path.read_text()

    print(f"\n  Pushing {pgn_path.name} → Lichess study '{study_name}'...")

    if not replace:
        print(
            "  ⚠ Note: Lichess import ADDS chapters. If chapters already exist,\n"
            "    duplicates will be created. Use --replace to be reminded of this."
        )

    try:
        result = client.studies.import_pgn(study_id, pgn_content)
        print(f"\n  ✓ Import successful!")
        print(f"  Study URL: https://lichess.org/study/{study_id}")
        if isinstance(result, list):
            print(f"  Chapters created: {len(result)}")
            for chapter in result:
                name = chapter.get("name", "Unnamed")
                print(f"    - {name}")
    except berserk.exceptions.ResponseError as e:
        error_exit(
            f"Failed to import PGN to Lichess: {e}",
            hint=f"Check that study '{study_name}' (id: {study_id}) exists\n"
            f"  and your token has study:write scope.",
        )


def pull_pgn(pgn_path: str | Path, *, in_place: bool = False) -> None:
    """Pull the latest PGN from a Lichess study to a local file.

    Args:
        pgn_path: Path to the PGN file (used to look up the study mapping).
        in_place: If True, overwrite the file. Otherwise write to *_from_lichess.pgn.
    """
    pgn_path = Path(pgn_path)
    config = load_config()
    from chess_opening_prep.config import get_study_mapping

    mapping = get_study_mapping(config, pgn_path.name)
    study_id = mapping["study_id"]
    study_name = mapping.get("study_name", study_id)

    client = _get_client()

    print(f"\n  Pulling Lichess study '{study_name}' → local...")

    try:
        pgn_data = client.studies.export(study_id)

        # berserk returns a generator of strings for study export
        if hasattr(pgn_data, "__iter__") and not isinstance(pgn_data, str):
            pgn_text = "\n".join(pgn_data)
        else:
            pgn_text = str(pgn_data)

        if in_place:
            output_path = pgn_path
        else:
            output_path = pgn_path.with_name(
                pgn_path.stem + "_from_lichess" + pgn_path.suffix
            )

        output_path.write_text(pgn_text)

        # Count chapters (games)
        chapter_count = pgn_text.count('[Event "')
        print(f"  ✓ Downloaded {chapter_count} chapter(s)")
        print(f"  Output: {output_path}")

    except berserk.exceptions.ResponseError as e:
        error_exit(
            f"Failed to export study from Lichess: {e}",
            hint=f"Check that study '{study_name}' (id: {study_id}) exists\n"
            f"  and your token has study:read scope.",
        )
