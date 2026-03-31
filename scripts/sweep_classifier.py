"""Automated parameter sweep for the !! and ! classifier.

Replaces manual worktree-based hypothesis testing with a fast in-process
evaluation loop. Preloads all data once, then evaluates hundreds of
config variations in seconds.

Phases:
  A — Single-parameter sensitivity analysis
  B — Greedy combination of best single-parameter improvements
  C — Random perturbation search around the best config
  D — Leave-One-Game-Out cross-validation on top candidates

Usage: uv run python3 scripts/sweep_classifier.py [--perturbations N]
"""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import pathlib
import random
import time
from dataclasses import dataclass, field

from chess_self_coach.classifier import (
    DEFAULT_CONFIG,
    COMPLEXITY_BUDGET,
    COMPLEXITY_LAMBDA,
    MIN_SCORE,
    classify_move,
    count_config_complexity,
    _compute_f1,
    _win_prob,
)
from chess_self_coach.config import tactics_data_path


# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class GameData:
    """Pre-loaded data for one ground truth game."""

    game_id: str
    moves: list[dict]
    brilliant_indices: set[int]
    great_indices: set[int]
    tactics: list[dict | None]


@dataclass
class PreloadedData:
    """All data needed to evaluate a config, loaded once."""

    games: list[GameData]
    total_moves: int = 0
    all_motif_names: set[str] = field(default_factory=set)


@dataclass
class ScoreResult:
    """Result of evaluating one config."""

    brilliant_tp: int
    brilliant_fp: int
    brilliant_fn: int
    brilliant_f1: float
    great_tp: int
    great_fp: int
    great_fn: int
    great_f1: float
    macro_f1: float
    complexity: int
    penalty: float
    score: float


# ── Preloading ───────────────────────────────────────────────────────────────


def preload_data() -> PreloadedData:
    """Load ground truth, cases, and tactics once."""
    gt_path = pathlib.Path("tests/e2e/fixtures/classification_ground_truth.json")
    with open(gt_path) as f:
        gt_data = json.load(f)

    spec = importlib.util.spec_from_file_location(
        "cases", "tests/e2e/classification_cases.py"
    )
    assert spec and spec.loader
    cases_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cases_mod)
    games_gt: list[dict] = cases_mod.GAMES  # type: ignore[attr-defined]

    gt_by_id = {g["game_id"]: g for g in gt_data["games"]}

    # Load tactics
    tactics_by_game: dict[str, list[dict]] = {}
    tp = tactics_data_path()
    if tp.exists():
        with open(tp) as f:
            tactics_by_game = json.load(f).get("games", {})

    games: list[GameData] = []
    total_moves = 0
    all_motifs: set[str] = set()

    for game_gt in games_gt:
        gid = game_gt["game_id"]
        gt_game = gt_by_id.get(gid)
        if not gt_game:
            continue
        moves = gt_game["moves"]
        total_moves += len(moves)

        # Find tactics by numeric ID
        num_id = gid.split("_")[-1]
        game_tactics_list: list[dict] | None = None
        for url, tac in tactics_by_game.items():
            if num_id in url:
                game_tactics_list = tac
                break

        tactics: list[dict | None] = []
        for i in range(len(moves)):
            t = game_tactics_list[i] if game_tactics_list and i < len(game_tactics_list) else None
            tactics.append(t)
            if t:
                for k, v in t.items():
                    if k != "_pv" and v is True:
                        all_motifs.add(k)

        games.append(GameData(
            game_id=gid,
            moves=moves,
            brilliant_indices=set(game_gt.get("brilliant_indices", [])),
            great_indices=set(game_gt.get("great_indices", [])),
            tactics=tactics,
        ))

    return PreloadedData(games=games, total_moves=total_moves, all_motif_names=all_motifs)


# ── Evaluation ───────────────────────────────────────────────────────────────


def evaluate_config(
    config: dict[str, object],
    data: PreloadedData,
    exclude_game: str | None = None,
) -> ScoreResult:
    """Evaluate a config against ground truth (fast, in-process).

    Args:
        config: Classifier parameters to test.
        data: Pre-loaded ground truth data.
        exclude_game: Game ID to exclude (for LOGO cross-validation).
    """
    total_brilliant = {"tp": 0, "fp": 0, "fn": 0}
    total_great = {"tp": 0, "fp": 0, "fn": 0}

    for game in data.games:
        if exclude_game and game.game_id == exclude_game:
            continue

        classifications: list[dict | None] = []
        for i, m in enumerate(game.moves):
            side = m.get("side", "white" if i % 2 == 0 else "black")
            prev = game.moves[i - 1] if i > 0 else None
            tact = game.tactics[i]
            classifications.append(classify_move(m, side, prev, tact, config))

        for i, cls in enumerate(classifications):
            predicted = cls["c"] if cls else "other"
            if predicted not in ("brilliant", "great"):
                predicted = "other"
            expected = (
                "brilliant" if i in game.brilliant_indices
                else "great" if i in game.great_indices
                else "other"
            )
            for cat, expected_cat, stats in [
                ("brilliant", "brilliant", total_brilliant),
                ("great", "great", total_great),
            ]:
                if expected == expected_cat and predicted == expected_cat:
                    stats["tp"] += 1
                elif predicted == expected_cat and expected != expected_cat:
                    stats["fp"] += 1
                elif expected == expected_cat and predicted != expected_cat:
                    stats["fn"] += 1

    _, _, brilliant_f1 = _compute_f1(total_brilliant["tp"], total_brilliant["fp"], total_brilliant["fn"])
    _, _, great_f1 = _compute_f1(total_great["tp"], total_great["fp"], total_great["fn"])
    macro_f1 = (brilliant_f1 + great_f1) / 2

    _, _, _, complexity = count_config_complexity(config)
    penalty = COMPLEXITY_LAMBDA * complexity / COMPLEXITY_BUDGET
    score = macro_f1 - penalty

    return ScoreResult(
        brilliant_tp=total_brilliant["tp"],
        brilliant_fp=total_brilliant["fp"],
        brilliant_fn=total_brilliant["fn"],
        brilliant_f1=brilliant_f1,
        great_tp=total_great["tp"],
        great_fp=total_great["fp"],
        great_fn=total_great["fn"],
        great_f1=great_f1,
        macro_f1=macro_f1,
        complexity=complexity,
        penalty=penalty,
        score=score,
    )


# ── Sweep phases ─────────────────────────────────────────────────────────────


def _make_config(**overrides: object) -> dict[str, object]:
    """Create a config with specific overrides applied to DEFAULT_CONFIG."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(overrides)
    return cfg


@dataclass
class SweepResult:
    """One sweep candidate with its config and score."""

    label: str
    config: dict[str, object]
    result: ScoreResult
    delta: float  # score - baseline score


def phase_a_sensitivity(data: PreloadedData, baseline: ScoreResult) -> list[SweepResult]:
    """Phase A: Single-parameter sensitivity analysis.

    Sweep each numeric threshold across a range, and test each tactical
    motif as a brilliant or great trigger.
    """
    results: list[SweepResult] = []

    # Numeric threshold sweeps
    sweep_ranges: dict[str, list[float]] = {
        "brilliant_epl_max": [-0.020, -0.015, -0.010, -0.008, -0.006, -0.005, -0.004, -0.003, -0.002, -0.001, 0.0],
        "brilliant_wp_min": [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40],
        "brilliant_wp_max": [0.80, 0.85, 0.90, 0.95, 0.98, 1.0],
        "great_epl_max": [0.0, 0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05],
        "great_opp_epl_min": [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30],
        "miss_epl_min": [0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10],
        "miss_opp_epl_min": [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25],
    }

    for param, values in sweep_ranges.items():
        current_val = DEFAULT_CONFIG[param]
        for val in values:
            if val == current_val:
                continue
            cfg = _make_config(**{param: val})
            r = evaluate_config(cfg, data)
            results.append(SweepResult(
                label=f"{param}={val}",
                config=cfg,
                result=r,
                delta=r.score - baseline.score,
            ))

    # Motif sweeps: test each motif as brilliant or great trigger
    for motif in sorted(data.all_motif_names):
        if motif in ("isSacrifice", "isMissedCapture"):
            continue  # already used

        # Test as brilliant motif
        cfg = _make_config(brilliant_motifs=["isSacrifice", motif])
        r = evaluate_config(cfg, data)
        results.append(SweepResult(
            label=f"brilliant_motif+{motif}",
            config=cfg,
            result=r,
            delta=r.score - baseline.score,
        ))

        # Test as great motif
        cfg = _make_config(great_motifs=[motif])
        r = evaluate_config(cfg, data)
        results.append(SweepResult(
            label=f"great_motif+{motif}",
            config=cfg,
            result=r,
            delta=r.score - baseline.score,
        ))

    results.sort(key=lambda x: x.delta, reverse=True)
    return results


def phase_b_greedy(
    data: PreloadedData,
    baseline: ScoreResult,
    phase_a_results: list[SweepResult],
) -> tuple[dict[str, object], ScoreResult, list[str]]:
    """Phase B: Greedy combination of best single-parameter improvements.

    Start from the best Phase A change, greedily add the next-best
    improvement until no further addition helps.
    """
    improvements = [r for r in phase_a_results if r.delta > 0]
    if not improvements:
        return copy.deepcopy(DEFAULT_CONFIG), baseline, []

    best_config = copy.deepcopy(improvements[0].config)
    best_score = improvements[0].result
    applied = [improvements[0].label]

    for candidate in improvements[1:]:
        # Merge candidate's overrides into best_config
        trial = copy.deepcopy(best_config)
        for k, v in candidate.config.items():
            if v != DEFAULT_CONFIG.get(k):
                trial[k] = v

        r = evaluate_config(trial, data)
        if r.score > best_score.score:
            best_config = trial
            best_score = r
            applied.append(candidate.label)

    return best_config, best_score, applied


def phase_c_random(
    data: PreloadedData,
    base_config: dict[str, object],
    base_score: ScoreResult,
    n_perturbations: int = 200,
) -> tuple[dict[str, object], ScoreResult]:
    """Phase C: Random perturbation search around the best config.

    Randomly perturb numeric thresholds by +/- 20% to explore
    non-linear interactions.
    """
    numeric_keys = [
        "brilliant_epl_max", "brilliant_wp_min", "brilliant_wp_max",
        "great_epl_max", "great_opp_epl_min",
        "miss_epl_min", "miss_opp_epl_min",
    ]

    best_config = copy.deepcopy(base_config)
    best_score = base_score

    for _ in range(n_perturbations):
        trial = copy.deepcopy(base_config)
        # Perturb 1-3 random numeric params
        n_params = random.randint(1, 3)
        for key in random.sample(numeric_keys, min(n_params, len(numeric_keys))):
            current = float(trial[key])  # type: ignore[arg-type]
            if current == 0:
                delta = random.uniform(-0.01, 0.01)
            else:
                delta = current * random.uniform(-0.20, 0.20)
            trial[key] = round(current + delta, 4)

        r = evaluate_config(trial, data)
        if r.score > best_score.score:
            best_config = trial
            best_score = r

    return best_config, best_score


def phase_d_logo(
    data: PreloadedData,
    candidates: list[tuple[str, dict[str, object]]],
) -> list[tuple[str, float, float, float]]:
    """Phase D: Leave-One-Game-Out cross-validation.

    For each candidate config, compute the average score when
    each game is excluded one at a time.

    Returns:
        List of (label, full_score, logo_score, divergence) tuples.
    """
    results: list[tuple[str, float, float, float]] = []

    for label, config in candidates:
        full = evaluate_config(config, data)

        logo_scores: list[float] = []
        for game in data.games:
            r = evaluate_config(config, data, exclude_game=game.game_id)
            logo_scores.append(r.score)

        logo_avg = sum(logo_scores) / len(logo_scores) if logo_scores else 0.0
        divergence = full.score - logo_avg
        results.append((label, full.score, logo_avg, divergence))

    return results


# ── Report ───────────────────────────────────────────────────────────────────


def _fmt_score(r: ScoreResult) -> str:
    """Format a score result as a compact string."""
    return (
        f"score={r.score:.3f} (F1={r.macro_f1:.3f} - penalty={r.penalty:.3f}) "
        f"[B: TP={r.brilliant_tp} FP={r.brilliant_fp} FN={r.brilliant_fn} F1={r.brilliant_f1:.3f}] "
        f"[G: TP={r.great_tp} FP={r.great_fp} FN={r.great_fn} F1={r.great_f1:.3f}]"
    )


def print_report(
    baseline: ScoreResult,
    phase_a: list[SweepResult],
    best_config: dict[str, object],
    best_score: ScoreResult,
    greedy_applied: list[str],
    random_config: dict[str, object],
    random_score: ScoreResult,
    logo_results: list[tuple[str, float, float, float]],
    elapsed: float,
) -> None:
    """Print the full sweep report to stdout."""
    print(f"\n{'='*70}")
    print("CLASSIFIER SWEEP REPORT")
    print(f"{'='*70}")

    print(f"\nBASELINE: {_fmt_score(baseline)}")

    # Phase A top results
    print(f"\n--- Phase A: Single-parameter sensitivity ({len(phase_a)} evaluations) ---")
    improvements = [r for r in phase_a if r.delta > 0]
    degradations = [r for r in phase_a if r.delta < 0]
    print(f"  {len(improvements)} improvements, {len(degradations)} degradations")

    print("\n  Top 10 improvements:")
    for r in phase_a[:10]:
        sign = "+" if r.delta >= 0 else ""
        print(f"    {sign}{r.delta:.4f}  {r.label:40s}  {_fmt_score(r.result)}")

    # Motif analysis
    print("\n  Motif analysis:")
    motif_results = [r for r in phase_a if "motif+" in r.label]
    brilliant_motifs = sorted(
        [r for r in motif_results if r.label.startswith("brilliant_")],
        key=lambda x: x.delta, reverse=True,
    )
    great_motifs = sorted(
        [r for r in motif_results if r.label.startswith("great_")],
        key=lambda x: x.delta, reverse=True,
    )

    if brilliant_motifs:
        print("    BRILLIANT motifs (top 5):")
        for r in brilliant_motifs[:5]:
            sign = "+" if r.delta >= 0 else ""
            print(f"      {sign}{r.delta:.4f}  {r.label}")
    if great_motifs:
        print("    GREAT motifs (top 5):")
        for r in great_motifs[:5]:
            sign = "+" if r.delta >= 0 else ""
            print(f"      {sign}{r.delta:.4f}  {r.label}")

    # Phase B
    print(f"\n--- Phase B: Greedy combination ---")
    print(f"  Applied: {', '.join(greedy_applied) if greedy_applied else '(none)'}")
    print(f"  Result: {_fmt_score(best_score)}")

    # Phase C
    print(f"\n--- Phase C: Random perturbation ---")
    print(f"  Result: {_fmt_score(random_score)}")
    if random_score.score > best_score.score:
        print("  Random search found a BETTER config!")

    # Phase D
    print(f"\n--- Phase D: Leave-One-Game-Out validation ---")
    for label, full, logo, div in logo_results:
        flag = " *** OVERFITTING RISK ***" if abs(div) > 0.03 else ""
        print(f"  {label:20s}  full={full:.3f}  LOGO={logo:.3f}  div={div:+.3f}{flag}")

    # Brilliant stability warning
    total_brilliant_labels = baseline.brilliant_tp + baseline.brilliant_fn
    if total_brilliant_labels < 10:
        print(f"\n  WARNING: Only {total_brilliant_labels} brilliant labels — F1 is inherently unstable")

    # Best config
    final_config = random_config if random_score.score > best_score.score else best_config
    final_score = random_score if random_score.score > best_score.score else best_score

    print(f"\n{'='*70}")
    print("BEST CONFIG FOUND:")
    print(f"{'='*70}")
    print(f"  Score: {final_score.score:.3f} (baseline: {baseline.score:.3f}, delta: {final_score.score - baseline.score:+.3f})")

    # Show config diff vs DEFAULT
    print("\n  Config changes vs DEFAULT:")
    for k in sorted(DEFAULT_CONFIG.keys()):
        default_val = DEFAULT_CONFIG[k]
        new_val = final_config[k]
        if new_val != default_val:
            print(f"    {k}: {default_val} -> {new_val}")

    if final_config == DEFAULT_CONFIG:
        print("    (no changes — DEFAULT_CONFIG is already optimal)")

    print(f"\n  Full config dict:")
    for k in sorted(final_config.keys()):
        print(f"    {k!r}: {final_config[k]!r},")

    print(f"\nTotal sweep time: {elapsed:.1f}s")
    print(f"{'='*70}")


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    """Run the full sweep pipeline."""
    import argparse

    parser = argparse.ArgumentParser(description="Sweep classifier parameters")
    parser.add_argument("--perturbations", type=int, default=200,
                        help="Number of random perturbations in Phase C (default: 200)")
    args = parser.parse_args()

    t0 = time.monotonic()

    print("Loading data...")
    data = preload_data()
    t_load = time.monotonic() - t0
    print(f"  {len(data.games)} games, {data.total_moves} moves, "
          f"{len(data.all_motif_names)} motifs ({t_load:.1f}s)")

    print("\nBaseline evaluation...")
    baseline = evaluate_config(DEFAULT_CONFIG, data)
    print(f"  {_fmt_score(baseline)}")

    print(f"\nPhase A: Sensitivity analysis...")
    t_a = time.monotonic()
    phase_a = phase_a_sensitivity(data, baseline)
    print(f"  {len(phase_a)} evaluations ({time.monotonic() - t_a:.1f}s)")

    print(f"\nPhase B: Greedy combination...")
    t_b = time.monotonic()
    best_config, best_score, greedy_applied = phase_b_greedy(data, baseline, phase_a)
    print(f"  {len(greedy_applied)} changes applied ({time.monotonic() - t_b:.1f}s)")

    print(f"\nPhase C: Random perturbation ({args.perturbations} trials)...")
    t_c = time.monotonic()
    random_config, random_score = phase_c_random(data, best_config, best_score, args.perturbations)
    print(f"  ({time.monotonic() - t_c:.1f}s)")

    print(f"\nPhase D: LOGO cross-validation...")
    t_d = time.monotonic()
    # Validate top candidates
    final_config = random_config if random_score.score > best_score.score else best_config
    final_score = random_score if random_score.score > best_score.score else best_score
    candidates: list[tuple[str, dict[str, object]]] = [
        ("baseline", copy.deepcopy(DEFAULT_CONFIG)),
        ("best_found", copy.deepcopy(final_config)),
    ]
    # Add top-3 Phase A results if they're different
    for r in phase_a[:3]:
        if r.delta > 0:
            candidates.append((r.label[:20], copy.deepcopy(r.config)))

    logo_results = phase_d_logo(data, candidates)
    print(f"  {len(candidates)} candidates x {len(data.games)} folds ({time.monotonic() - t_d:.1f}s)")

    elapsed = time.monotonic() - t0

    print_report(
        baseline=baseline,
        phase_a=phase_a,
        best_config=best_config,
        best_score=best_score,
        greedy_applied=greedy_applied,
        random_config=random_config,
        random_score=random_score,
        logo_results=logo_results,
        elapsed=elapsed,
    )

    # Save results to JSON
    output = {
        "baseline": {
            "score": baseline.score,
            "macro_f1": baseline.macro_f1,
            "brilliant": {"tp": baseline.brilliant_tp, "fp": baseline.brilliant_fp, "fn": baseline.brilliant_fn},
            "great": {"tp": baseline.great_tp, "fp": baseline.great_fp, "fn": baseline.great_fn},
        },
        "best_config": final_config,
        "best_score": final_score.score,
        "best_macro_f1": final_score.macro_f1,
        "delta": final_score.score - baseline.score,
        "logo_results": [
            {"label": label, "full": full, "logo": logo, "divergence": div}
            for label, full, logo, div in logo_results
        ],
        "phase_a_top10": [
            {"label": r.label, "delta": r.delta, "score": r.result.score}
            for r in phase_a[:10]
        ],
        "elapsed_seconds": elapsed,
    }

    out_path = pathlib.Path("/tmp/sweep_results.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
