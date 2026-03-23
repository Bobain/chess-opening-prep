"""Lichess Cloud Eval API client.

Queries the Lichess cloud evaluation database for pre-computed Stockfish
evaluations. Opening positions have near-perfect coverage at depth 50-70,
making this much faster than running Stockfish locally.

API: https://lichess.org/api#tag/Analysis
"""

from __future__ import annotations

import time

import requests

_URL = "https://lichess.org/api/cloud-eval"

_TIMEOUT = 10.0

_RATE_LIMIT_DELAY = 0.1


def query_cloud_eval(fen: str, multi_pv: int = 1) -> dict | None:
    """Query the Lichess Cloud Eval for a position.

    Args:
        fen: FEN string of the position to query.
        multi_pv: Number of principal variations to request.

    Returns:
        API response dict with {fen, knodes, depth, pvs[]} or None if
        the position is not in the database or the API is unavailable.
    """
    params = {"fen": fen, "multiPv": multi_pv}

    try:
        resp = requests.get(_URL, params=params, timeout=_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            time.sleep(1.0)
            resp = requests.get(_URL, params=params, timeout=_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
    except (requests.RequestException, ValueError):
        pass

    return None
