"""Shared I/O utilities for chess-self-coach.

Atomic file writes, JSON helpers, and other filesystem operations.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, data: dict[str, Any], *, pretty: bool = False) -> None:
    """Write JSON atomically: temp file, fsync, os.replace.

    Args:
        path: Target file path.
        data: Dict to serialize as JSON.
        pretty: If True, write indented JSON. Default: compact (minified).
    """
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            if pretty:
                json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
