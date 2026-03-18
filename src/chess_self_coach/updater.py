"""Self-update mechanism for chess-self-coach."""

from __future__ import annotations

import shutil
import subprocess
import sys


def update() -> None:
    """Update chess-self-coach to the latest version via pipx or pip."""
    if shutil.which("pipx"):
        print("Updating via pipx...")
        result = subprocess.run(
            ["pipx", "upgrade", "chess-self-coach"],
            capture_output=True,
            text=True,
        )
        print(result.stdout.strip())
        if result.returncode != 0:
            print(f"Update failed: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Updating via pip...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "chess-self-coach"],
            check=True,
        )
    print("\n✓ Update complete!")
