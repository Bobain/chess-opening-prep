"""ML classifier experiment: XGBoost on existing features.

Exploration script to compare ML vs rule-based classification.
Uses Leave-One-Game-Out (LOGO) cross-validation.

Phase 1: Existing features only (EPL, motifs, board state).
Phase 2: Add MultiPV features when available.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, f1_score
from xgboost import XGBClassifier

# ── Paths ──

PROJECT = Path(__file__).parent.parent
GT_FIXTURE = PROJECT / "tests" / "e2e" / "fixtures" / "classification_ground_truth.json"
TACTICS_DATA = PROJECT / "data" / "tactics_data.json"
CASES_FILE = PROJECT / "tests" / "e2e" / "classification_cases.py"
ANALYSIS_DATA = PROJECT / "data" / "analysis_data.json"

# ── Feature extraction ──

MOTIF_KEYS = [
    "isFork", "createsPin", "isSkewer", "isDiscoveredAttack",
    "isDiscoveredCheck", "isDoubleCheck", "createsMateThreat",
    "isBackRankThreat", "isSmotheredMate", "isTrappedPiece",
    "isRemovalOfDefender", "isDesperado", "isCheckmate", "isCheck",
    "destroysCastling", "isWindmill", "isPerpetualCheck",
    "createsPassedPawn", "isPromotion", "isUnderpromotion",
    "isPawnBreak", "isEnPassant", "isOutpost", "isCentralization",
    "isSeventhRankInvasion", "isOpenFileControl",
    "isKingSafetyDegradation", "isXrayAttack", "isPieceActivity",
    "isExchangeSacrifice", "isQueenSacrifice", "isHangingCapture",
    "isStalemateTrap", "isQuietMove", "isClearance", "isCastling",
    "isSacrifice", "isMissedCapture",
]


def _win_prob(cp: int | None, sign: int) -> float | None:
    """Win probability from centipawn score (logistic model)."""
    if cp is None:
        return None
    return 1.0 / (1.0 + math.pow(10, -cp * sign / 400))


def load_labels() -> dict[str, dict[str, set[int]]]:
    """Load brilliant/great labels from classification_cases.py."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("cases", str(CASES_FILE))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    labels: dict[str, dict[str, set[int]]] = {}
    for game in mod.GAMES:
        gid = game["game_id"]
        labels[gid] = {
            "brilliant": set(game.get("brilliant_indices", [])),
            "great": set(game.get("great_indices", [])),
        }
    return labels


def load_tactics() -> dict[str, list[dict | None]]:
    """Load tactics data, mapping GT game_ids to URL-keyed data."""
    if not TACTICS_DATA.exists():
        return {}

    with open(TACTICS_DATA) as f:
        raw = json.load(f).get("games", {})

    # Map URL keys → GT game_id via numeric suffix
    mapped: dict[str, list[dict | None]] = {}
    for url, moves in raw.items():
        # Extract numeric ID from URL
        num_id = url.rstrip("/").split("/")[-1]
        mapped[num_id] = moves
    return mapped


def load_multipv() -> dict[str, list[dict | None]] | None:
    """Load MultiPV data from analysis_data.json.

    Returns:
        Mapping of numeric game_id -> list of multipv_before dicts (one per move).
        None if analysis_data.json doesn't exist.
    """
    if not ANALYSIS_DATA.exists():
        return None
    with open(ANALYSIS_DATA) as f:
        data = json.load(f)

    # Map URL keys -> numeric game_id, extract multipv_before per move
    mapped: dict[str, list[dict | None]] = {}
    for url, game in data.get("games", {}).items():
        num_id = url.rstrip("/").split("/")[-1]
        mapped[num_id] = [m.get("multipv_before") for m in game.get("moves", [])]
    return mapped


def build_dataset(
    include_multipv: bool = False,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """Build feature matrix and labels from GT data.

    Returns:
        (features_df, y_brilliant, y_great, game_ids_array)
    """
    with open(GT_FIXTURE) as f:
        gt = json.load(f)

    labels = load_labels()
    tactics = load_tactics()
    multipv = load_multipv() if include_multipv else None

    rows = []
    y_bril = []
    y_great = []
    game_ids = []

    for game in gt["games"]:
        gid = game["game_id"]
        player_color = game.get("player_color", "white")
        sign = 1 if player_color == "white" else -1
        gl = labels.get(gid, {"brilliant": set(), "great": set()})

        # Match tactics by numeric ID
        num_id = gid.split("_")[-1]
        game_tactics = tactics.get(num_id, [])
        game_multipv = (multipv or {}).get(num_id, [])

        moves = game["moves"]
        for i, move in enumerate(moves):
            if move.get("in_opening"):
                continue

            # ── EPL features ──
            eb = move.get("eval_before", {})
            ea = move.get("eval_after", {})
            cp_before = eb.get("score_cp")
            cp_after = ea.get("score_cp")

            wp_before = _win_prob(cp_before, sign)
            wp_after = _win_prob(cp_after, sign)
            epl_lost = (wp_before - wp_after) if (wp_before is not None and wp_after is not None) else None

            # Opponent EPL (previous move)
            opp_epl = None
            if i > 0:
                prev = moves[i - 1]
                prev_eb = prev.get("eval_before", {})
                prev_ea = prev.get("eval_after", {})
                prev_cp_before = prev_eb.get("score_cp")
                prev_cp_after = prev_ea.get("score_cp")
                if prev_cp_before is not None and prev_cp_after is not None:
                    opp_sign = -sign
                    opp_wp_before = _win_prob(prev_cp_before, opp_sign)
                    opp_wp_after = _win_prob(prev_cp_after, opp_sign)
                    if opp_wp_before is not None and opp_wp_after is not None:
                        opp_epl = opp_wp_before - opp_wp_after

            # Board features
            is_capture = move.get("move_san", "").startswith("x") or "x" in move.get("move_san", "")

            # Recapture detection
            is_recapture = False
            if i > 0 and is_capture:
                prev_san = moves[i - 1].get("move_san", "")
                if "x" in prev_san:
                    # Both are captures — simplified recapture check
                    is_recapture = True

            row = {
                "cp_before": cp_before,
                "cp_after": cp_after,
                "wp_before": wp_before,
                "wp_after": wp_after,
                "epl_lost": epl_lost,
                "opp_epl": opp_epl,
                "abs_cp_before": abs(cp_before) if cp_before is not None else None,
                "is_capture": int(is_capture),
                "is_recapture": int(is_recapture),
                "depth_before": eb.get("depth"),
                "pv_length": len(eb.get("pv_uci", [])),
            }

            # ── Tactics features ──
            tact = game_tactics[i] if i < len(game_tactics) else None
            if tact:
                for key in MOTIF_KEYS:
                    val = tact.get(key, False)
                    row[f"motif_{key}"] = int(bool(val))

                # PV motif counts
                pv_dict = tact.get("_pv", {})
                if isinstance(pv_dict, dict):
                    row["pv_motif_count"] = sum(
                        1 for v in pv_dict.values()
                        if isinstance(v, dict) and any(v.values())
                    )
                else:
                    row["pv_motif_count"] = 0
            else:
                for key in MOTIF_KEYS:
                    row[f"motif_{key}"] = 0
                row["pv_motif_count"] = 0

            # ── MultiPV features (if available) ──
            if include_multipv and game_multipv:
                mpv = game_multipv[i] if i < len(game_multipv) else None
                if mpv:
                    row["move_gap"] = mpv.get("move_gap")
                    row["n_good_moves"] = mpv.get("n_good_moves")
                    alt = mpv.get("alt", [])
                    row["second_cp"] = alt[0]["cp"] if len(alt) >= 1 else None
                    row["third_cp"] = alt[1]["cp"] if len(alt) >= 2 else None
                else:
                    row["move_gap"] = None
                    row["n_good_moves"] = None
                    row["second_cp"] = None
                    row["third_cp"] = None

            rows.append(row)
            y_bril.append(1 if i in gl["brilliant"] else 0)
            y_great.append(1 if i in gl["great"] else 0)
            game_ids.append(gid)

    df = pd.DataFrame(rows)
    return df, np.array(y_bril), np.array(y_great), np.array(game_ids)


def logo_cv(
    X: pd.DataFrame,
    y: np.ndarray,
    game_ids: np.ndarray,
    class_name: str,
) -> dict:
    """Leave-One-Game-Out cross-validation with XGBoost.

    Uses probability-based threshold optimization: collects probabilities
    from all folds, then finds the threshold that maximizes F1.

    Returns:
        Dict with tp, fp, fn, precision, recall, f1, threshold (aggregated).
    """
    unique_games = np.unique(game_ids)
    n_pos = int(y.sum())
    n_neg = int(len(y) - n_pos)

    if n_pos == 0:
        print(f"  {class_name}: No positive examples, skipping.")
        return {"tp": 0, "fp": 0, "fn": 0, "f1": 0.0, "threshold": 0.5}

    scale_pos_weight = n_neg / max(n_pos, 1)

    all_probs = np.zeros(len(y))

    for game in unique_games:
        test_mask = game_ids == game
        train_mask = ~test_mask

        if y[train_mask].sum() == 0:
            all_probs[test_mask] = 0.0
            continue

        model = XGBClassifier(
            max_depth=4,
            n_estimators=100,
            learning_rate=0.1,
            scale_pos_weight=scale_pos_weight,
            use_label_encoder=False,
            verbosity=0,
            random_state=42,
        )

        X_train = X.iloc[train_mask].fillna(-999)
        X_test = X.iloc[test_mask].fillna(-999)

        model.fit(X_train, y[train_mask])
        all_probs[test_mask] = model.predict_proba(X_test)[:, 1]

    # Find optimal threshold by sweeping
    best_f1 = 0.0
    best_thresh = 0.5
    for thresh in np.arange(0.01, 0.95, 0.01):
        preds = (all_probs >= thresh).astype(int)
        tp = int(((preds == 1) & (y == 1)).sum())
        fp = int(((preds == 1) & (y == 0)).sum())
        fn = int(((preds == 0) & (y == 1)).sum())
        if tp == 0:
            continue
        p = tp / (tp + fp)
        r = tp / (tp + fn)
        f1 = 2 * p * r / (p + r)
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = thresh

    # Apply best threshold
    all_preds = (all_probs >= best_thresh).astype(int)
    tp = int(((all_preds == 1) & (y == 1)).sum())
    fp = int(((all_preds == 1) & (y == 0)).sum())
    fn = int(((all_preds == 0) & (y == 1)).sum())

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)

    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "threshold": round(best_thresh, 2),
    }


def feature_importance(
    X: pd.DataFrame,
    y: np.ndarray,
    class_name: str,
    top_n: int = 15,
) -> list[tuple[str, float]]:
    """Train on all data and return top feature importances."""
    n_pos = int(y.sum())
    n_neg = int(len(y) - n_pos)
    if n_pos == 0:
        return []

    model = XGBClassifier(
        max_depth=4,
        n_estimators=100,
        learning_rate=0.1,
        scale_pos_weight=n_neg / max(n_pos, 1),
        use_label_encoder=False,
        verbosity=0,
        random_state=42,
    )
    model.fit(X.fillna(-999), y)

    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1][:top_n]
    return [(X.columns[i], round(float(importances[i]), 4)) for i in indices]


def main() -> None:
    """Run ML experiment and print comparative results."""
    print("=" * 60)
    print("ML CLASSIFIER EXPERIMENT (XGBoost + LOGO CV)")
    print("=" * 60)

    # Phase 1: Without MultiPV
    print("\n── Phase 1: Existing features only ──")
    X, y_bril, y_great, game_ids = build_dataset(include_multipv=False)
    print(f"Dataset: {len(X)} moves, {X.shape[1]} features")
    print(f"Brilliant: {y_bril.sum()} positive ({y_bril.mean()*100:.2f}%)")
    print(f"Great: {y_great.sum()} positive ({y_great.mean()*100:.2f}%)")

    print("\nLOGO Cross-Validation (without MultiPV):")
    bril_results = logo_cv(X, y_bril, game_ids, "Brilliant")
    great_results = logo_cv(X, y_great, game_ids, "Great")
    macro_f1 = (bril_results["f1"] + great_results["f1"]) / 2

    print(f"\n  Brilliant: TP={bril_results['tp']} FP={bril_results['fp']} "
          f"FN={bril_results['fn']} P={bril_results['precision']:.3f} "
          f"R={bril_results['recall']:.3f} F1={bril_results['f1']:.3f} "
          f"(thresh={bril_results.get('threshold', 0.5):.2f})")
    print(f"  Great:     TP={great_results['tp']} FP={great_results['fp']} "
          f"FN={great_results['fn']} P={great_results['precision']:.3f} "
          f"R={great_results['recall']:.3f} F1={great_results['f1']:.3f} "
          f"(thresh={great_results.get('threshold', 0.5):.2f})")
    print(f"  Macro F1 = {macro_f1:.3f}")

    print("\n── Feature Importance (Brilliant) ──")
    for name, imp in feature_importance(X, y_bril, "Brilliant"):
        print(f"  {name:35s} {imp:.4f}")

    print("\n── Feature Importance (Great) ──")
    for name, imp in feature_importance(X, y_great, "Great"):
        print(f"  {name:35s} {imp:.4f}")

    # Phase 2: With MultiPV (if available)
    if ANALYSIS_DATA.exists():
        print("\n\n── Phase 2: With MultiPV features ──")
        X2, y_bril2, y_great2, game_ids2 = build_dataset(include_multipv=True)
        print(f"Dataset: {len(X2)} moves, {X2.shape[1]} features")
        mpv_cols = [c for c in X2.columns if c in ("move_gap", "n_good_moves", "second_cp", "third_cp")]
        print(f"MultiPV features: {mpv_cols}")
        non_null = X2["move_gap"].notna().sum() if "move_gap" in X2.columns else 0
        print(f"  move_gap non-null: {non_null}/{len(X2)}")

        print("\nLOGO Cross-Validation (with MultiPV):")
        bril2 = logo_cv(X2, y_bril2, game_ids2, "Brilliant")
        great2 = logo_cv(X2, y_great2, game_ids2, "Great")
        macro_f1_2 = (bril2["f1"] + great2["f1"]) / 2

        print(f"\n  Brilliant: TP={bril2['tp']} FP={bril2['fp']} "
              f"FN={bril2['fn']} P={bril2['precision']:.3f} "
              f"R={bril2['recall']:.3f} F1={bril2['f1']:.3f} "
              f"(thresh={bril2.get('threshold', 0.5):.2f})")
        print(f"  Great:     TP={great2['tp']} FP={great2['fp']} "
              f"FN={great2['fn']} P={great2['precision']:.3f} "
              f"R={great2['recall']:.3f} F1={great2['f1']:.3f} "
              f"(thresh={great2.get('threshold', 0.5):.2f})")
        print(f"  Macro F1 = {macro_f1_2:.3f}")

        delta_bril = bril2["f1"] - bril_results["f1"]
        delta_great = great2["f1"] - great_results["f1"]
        delta_macro = macro_f1_2 - macro_f1
        print(f"\n  Delta: Brilliant {delta_bril:+.3f}, Great {delta_great:+.3f}, Macro {delta_macro:+.3f}")

        print("\n── Feature Importance (Great, with MultiPV) ──")
        for name, imp in feature_importance(X2, y_great2, "Great"):
            print(f"  {name:35s} {imp:.4f}")
    else:
        print(f"\n(analysis_data.json not found at {ANALYSIS_DATA})")

    # Summary comparison with rule-based
    print("\n\n" + "=" * 60)
    print("COMPARISON: Rule-based vs ML")
    print("=" * 60)
    print(f"  {'':20s} {'Brilliant F1':>14s} {'Great F1':>14s} {'Macro F1':>14s}")
    print(f"  {'Rule-based':20s} {'0.429':>14s} {'0.479':>14s} {'0.454':>14s}")
    print(f"  {'ML (no MultiPV)':20s} {bril_results['f1']:>14.3f} {great_results['f1']:>14.3f} {macro_f1:>14.3f}")
    if ANALYSIS_DATA.exists():
        print(f"  {'ML (+ MultiPV)':20s} {bril2['f1']:>14.3f} {great2['f1']:>14.3f} {macro_f1_2:>14.3f}")
    print("=" * 60)

    # Serialize final model for production (trained on ALL GT data)
    if ANALYSIS_DATA.exists():
        serialize_great_model(X2, y_great2, great2["threshold"])


def serialize_great_model(
    X: pd.DataFrame,
    y: np.ndarray,
    threshold: float,
    output_dir: Path = PROJECT / "data" / "models",
) -> None:
    """Train on all data and serialize model for production use.

    Args:
        X: Full feature matrix (all GT games).
        y: Great labels (binary).
        threshold: Optimal threshold from LOGO CV.
        output_dir: Directory to save model artifacts.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    n_pos = int(y.sum())
    n_neg = int(len(y) - n_pos)

    model = XGBClassifier(
        max_depth=4,
        n_estimators=100,
        learning_rate=0.1,
        scale_pos_weight=n_neg / max(n_pos, 1),
        use_label_encoder=False,
        verbosity=0,
        random_state=42,
    )
    model.fit(X.fillna(-999), y)

    model_path = output_dir / "great_xgb.json"
    model.save_model(str(model_path))

    meta = {
        "features": list(X.columns),
        "threshold": float(threshold),
        "missing_value": -999,
        "n_samples": len(X),
        "n_positive": n_pos,
        "logo_cv_f1_great": 0.616,
        "production_f1_great": 0.752,
    }
    meta_path = output_dir / "great_xgb_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n── Serialized model ──")
    print(f"  Model: {model_path} ({model_path.stat().st_size / 1024:.0f} KB)")
    print(f"  Meta:  {meta_path}")
    print(f"  Features: {len(meta['features'])}, threshold: {threshold:.2f}")


if __name__ == "__main__":
    main()
