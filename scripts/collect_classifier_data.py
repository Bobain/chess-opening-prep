"""Collect all !! and ! classified moves (TP/FP/FN) with 3-move context.

Uses the real JS classifier via Playwright (window._classifyMove).
Outputs to /tmp/classifier_data.json.

Usage: uv run python3 scripts/collect_classifier_data.py
"""

from __future__ import annotations

import json
import pathlib

from playwright.sync_api import sync_playwright


def wp(cp: int, sign: int) -> float:
    """Win probability from centipawn score."""
    return 1 / (1 + 10 ** (-cp * sign / 400))


def fmt_move(moves: list[dict], idx: int) -> dict | None:
    """Format a move with its eval context."""
    if idx < 0 or idx >= len(moves):
        return None
    m = moves[idx]
    eb = m.get("eval_before", {})
    ea = m.get("eval_after", {})
    san = m.get("move_san", "?")

    # Derive features from SAN notation
    is_capture = "x" in san
    is_check = "+" in san or "#" in san
    is_promotion = "=" in san
    # Piece moved: uppercase letter at start, or pawn if lowercase/none
    piece_moved = san[0] if san and san[0].isupper() else "P"

    return {
        "label": f"{(idx // 2) + 1}.{'w' if idx % 2 == 0 else 'b'}",
        "san": san,
        "fen": m.get("fen_before", ""),
        "cp_b": eb.get("score_cp"),
        "cp_a": ea.get("score_cp"),
        "is_mate": eb.get("is_mate", False),
        "mate_in": eb.get("mate_in"),
        "best": eb.get("best_move_san", "?"),
        "best_uci": eb.get("best_move_uci"),
        "is_best": m.get("move_uci") == eb.get("best_move_uci"),
        "pv": " ".join(eb.get("pv_san", [])[:6]),
        "pv_len": len(eb.get("pv_uci", [])),
        "is_capture": is_capture,
        "is_check": is_check,
        "is_promotion": is_promotion,
        "piece_moved": piece_moved,
    }


def main() -> None:
    """Collect classification data."""
    gt_path = pathlib.Path("tests/e2e/fixtures/classification_ground_truth.json")
    with open(gt_path) as f:
        gt_data = json.load(f)

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "cases", "tests/e2e/classification_cases.py"
    )
    assert spec and spec.loader
    cases_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cases_mod)
    GAMES = cases_mod.GAMES  # type: ignore[attr-defined]

    gt_by_id = {g["game_id"]: g for g in gt_data["games"]}
    results: dict[str, list[dict]] = {"brilliant": [], "great": []}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("http://localhost:8000")
        # Wait for full app init: game cards rendered means chess.js is loaded
        page.wait_for_selector(".game-card", timeout=30000)
        # Extra wait for JS init to complete
        page.wait_for_function(
            "() => typeof window._classifyMove === 'function'",
            timeout=10000,
        )

        for game_gt in GAMES:
            gid = game_gt["game_id"]
            gt_game = gt_by_id.get(gid)
            if not gt_game:
                continue
            moves = gt_game["moves"]
            brilliant_set = set(game_gt.get("brilliant_indices", []))
            great_set = set(game_gt.get("great_indices", []))

            moves_json = json.dumps(moves)
            classified = page.evaluate(
                f"""() => {{
                const moves = {moves_json};
                return moves.map((m, i) => {{
                    const side = m.side || (i % 2 === 0 ? 'white' : 'black');
                    const prevMove = i > 0 ? moves[i - 1] : null;
                    const cls = window._classifyMove(m, side, prevMove);
                    const cat = cls ? cls.category : 'other';
                    const sac = window._isSacrifice(m);
                    return {{ category: cat, is_sacrifice: sac }};
                }});
            }}"""
            )

            for i, (m, cls_result) in enumerate(zip(moves, classified)):
                predicted = cls_result["category"]
                is_sacrifice = cls_result["is_sacrifice"]
                if predicted not in ("brilliant", "great"):
                    predicted = "other"
                expected = (
                    "brilliant"
                    if i in brilliant_set
                    else "great"
                    if i in great_set
                    else "other"
                )
                if expected == "other" and predicted == "other":
                    continue

                side = "white" if i % 2 == 0 else "black"
                sign = 1 if side == "white" else -1

                opp_epl = None
                if i > 0:
                    prev = moves[i - 1]
                    peb = prev.get("eval_before", {})
                    pea = prev.get("eval_after", {})
                    if (
                        peb.get("score_cp") is not None
                        and pea.get("score_cp") is not None
                        and not peb.get("is_mate")
                        and not pea.get("is_mate")
                    ):
                        opp_sign = -sign
                        opp_epl = round(
                            wp(peb["score_cp"], opp_sign)
                            - wp(pea["score_cp"], opp_sign),
                            4,
                        )

                eb = m.get("eval_before", {})
                ea = m.get("eval_after", {})
                wp_b = wp_a = epl = wp_gain = cp_gain = None
                if eb.get("score_cp") is not None and not eb.get("is_mate"):
                    wp_b = round(wp(eb["score_cp"], sign), 4)
                    if ea.get("score_cp") is not None and not ea.get("is_mate"):
                        wp_a = round(wp(ea["score_cp"], sign), 4)
                        epl = round(wp_b - wp_a, 4)
                        wp_gain = round(wp_a - wp_b, 4)
                        cp_gain = (ea["score_cp"] - eb["score_cp"]) * sign

                status = (
                    "TP"
                    if expected == predicted
                    else ("FN" if expected in ("brilliant", "great") else "FP")
                )
                cat = (
                    "brilliant"
                    if "brilliant" in (expected, predicted)
                    else "great"
                )
                # Classification of the previous move (opponent's move)
                prev_cls_result = classified[i - 1] if i > 0 else {"category": "other"}
                prev_classification = prev_cls_result["category"]
                if prev_classification not in (
                    "brilliant", "great", "best", "excellent",
                    "good", "miss", "inaccuracy", "mistake", "blunder",
                ):
                    prev_classification = "other"

                # Is recapture? (same destination square as previous move)
                is_recapture = False
                if i > 0 and moves[i - 1].get("move_uci") and m.get("move_uci"):
                    is_recapture = (
                        moves[i - 1]["move_uci"][2:4] == m["move_uci"][2:4]
                    )

                move_fmt = fmt_move(moves, i)
                results[cat].append(
                    {
                        "game": gid[:30],
                        "idx": i,
                        "status": status,
                        "predicted": predicted,
                        "expected": expected,
                        # Win probability features
                        "wp_before": wp_b,
                        "wp_after": wp_a,
                        "epl_lost": epl,
                        "wp_gain": wp_gain,
                        "cp_gain": cp_gain,
                        "opp_epl": opp_epl,
                        # Move features
                        "is_sacrifice": is_sacrifice,
                        "is_recapture": is_recapture,
                        "is_capture": move_fmt.get("is_capture") if move_fmt else None,
                        "is_check": move_fmt.get("is_check") if move_fmt else None,
                        "piece_moved": move_fmt.get("piece_moved") if move_fmt else None,
                        "pv_len": move_fmt.get("pv_len") if move_fmt else None,
                        # Context
                        "prev_classification": prev_classification,
                        "in_opening": m.get("in_opening", False),
                        # Detailed move data
                        "before": fmt_move(moves, i - 1),
                        "move": move_fmt,
                        "after": fmt_move(moves, i + 1),
                    }
                )

        browser.close()

    for cat in ("brilliant", "great"):
        entries = results[cat]
        tp = sum(1 for e in entries if e["status"] == "TP")
        fp = sum(1 for e in entries if e["status"] == "FP")
        fn = sum(1 for e in entries if e["status"] == "FN")
        print(
            f"{cat}: TP={tp} FP={fp} FN={fn} (total {len(entries)} moves)"
        )

    # Save full data
    out = pathlib.Path("/tmp/classifier_data.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    total = sum(len(v) for v in results.values())
    print(f"\nSaved to {out} ({total} moves)")

    # Prepare batches for agent analysis (~15 moves each, mixing TP/FP/FN)
    all_moves = []
    for cat in ("brilliant", "great"):
        for entry in results[cat]:
            entry["category"] = cat
            all_moves.append(entry)

    batch_size = 15
    batches = [
        all_moves[i : i + batch_size]
        for i in range(0, len(all_moves), batch_size)
    ]

    batches_out = pathlib.Path("/tmp/classifier_batches.json")
    with open(batches_out, "w") as f:
        json.dump(batches, f, indent=2)
    print(f"Prepared {len(batches)} batches of ~{batch_size} moves → {batches_out}")

    # Format each batch as human-readable text for agent prompts
    for batch_idx, batch in enumerate(batches):
        lines: list[str] = []
        for e in batch:
            m = e.get("move") or {}
            b = e.get("before") or {}
            a = e.get("after") or {}
            lines.append(
                f'### {e["game"]} idx={e["idx"]} {m.get("label","?")} '
                f'{m.get("san","?")} — {e["status"]} '
                f'({e["category"]}: predicted={e["predicted"]}, '
                f'expected={e["expected"]})'
            )
            prev_cls = e.get("prev_classification", "?")
            lines.append(
                f'wp={e["wp_before"]} epl={e["epl_lost"]} wpGain={e.get("wp_gain")} '
                f'cpGain={e.get("cp_gain")} oppEPL={e["opp_epl"]} '
                f'is_best={m.get("is_best","?")} sac={e.get("is_sacrifice")} '
                f'recap={e.get("is_recapture")} prev_class={prev_cls}'
            )
            if b:
                best_tag = "" if b.get("is_best") else f' (best: {b.get("best","?")})'
                mate_tag = f' MATE={b.get("mate_in")}' if b.get("is_mate") else ""
                lines.append(
                    f'  BEFORE: {b["label"]} {b["san"]} '
                    f'cp={b["cp_b"]}→{b["cp_a"]}{mate_tag}{best_tag}'
                )
                lines.append(f'    PV: {b.get("pv","")}')
            mate_tag = f' MATE={m.get("mate_in")}' if m.get("is_mate") else ""
            lines.append(
                f'  MOVE: {m["label"]} {m["san"]} '
                f'cp={m["cp_b"]}→{m["cp_a"]}{mate_tag}'
            )
            lines.append(f'    FEN: {m.get("fen","")[:60]}')
            lines.append(f'    PV: {m.get("pv","")}')
            if a:
                lines.append(
                    f'  AFTER: {a["label"]} {a["san"]} '
                    f'cp={a["cp_b"]}→{a["cp_a"]}'
                )
            lines.append("")

        batch_file = pathlib.Path(f"/tmp/batch_{batch_idx}.txt")
        batch_file.write_text("\n".join(lines))

    print(
        f"Formatted {len(batches)} batch text files "
        f"(/tmp/batch_0.txt .. /tmp/batch_{len(batches)-1}.txt)"
    )

    # === Feature statistics for rule derivation ===
    print("\n=== FEATURE STATISTICS (TP vs FP vs FN) ===")

    numeric_features = [
        "wp_before", "wp_after", "epl_lost", "wp_gain", "cp_gain",
        "opp_epl", "pv_len",
    ]
    boolean_features = [
        "is_sacrifice", "is_recapture", "is_capture", "is_check", "in_opening",
    ]
    categorical_features = ["prev_classification", "piece_moved"]

    for cat in ("brilliant", "great"):
        print(f"\n{'='*60}")
        print(f"  {cat.upper()}")
        print(f"{'='*60}")

        by_status: dict[str, list[dict]] = {"TP": [], "FP": [], "FN": []}
        for e in results[cat]:
            by_status[e["status"]].append(e)

        # Numeric features: show median/mean per status
        for feat in numeric_features:
            print(f"\n  {feat}:")
            for status in ("TP", "FP", "FN"):
                vals = [e[feat] for e in by_status[status] if e.get(feat) is not None]
                if not vals:
                    print(f"    {status}: (no data)")
                    continue
                vals.sort()
                med = vals[len(vals) // 2]
                avg = sum(vals) / len(vals)
                lo, hi = vals[0], vals[-1]
                print(f"    {status} (n={len(vals):>3}): med={med:>8.4f}  avg={avg:>8.4f}  [{lo:.4f} .. {hi:.4f}]")

        # Boolean features: show % True per status
        for feat in boolean_features:
            print(f"\n  {feat}:")
            for status in ("TP", "FP", "FN"):
                entries = by_status[status]
                if not entries:
                    continue
                true_count = sum(1 for e in entries if e.get(feat))
                pct = 100 * true_count / len(entries) if entries else 0
                print(f"    {status} (n={len(entries):>3}): {true_count:>3}/{len(entries)} = {pct:>5.1f}%")

        # Categorical features: show distribution per status
        for feat in categorical_features:
            print(f"\n  {feat}:")
            for status in ("TP", "FP", "FN"):
                entries = by_status[status]
                if not entries:
                    continue
                counts: dict[str, int] = {}
                for e in entries:
                    v = str(e.get(feat, "?"))
                    counts[v] = counts.get(v, 0) + 1
                dist = ", ".join(
                    f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])
                )
                print(f"    {status} (n={len(entries):>3}): {dist}")

        # Per-move detail for small groups (FN, FP)
        for status in ("FN", "FP"):
            entries = by_status[status]
            if not entries or len(entries) > 20:
                continue
            print(f"\n  --- {status} {cat} detail ({len(entries)} moves) ---")
            for e in entries:
                m = e.get("move") or {}

                def _f(v: object) -> str:
                    return f"{v:.4f}" if isinstance(v, float) else str(v) if v is not None else "?"

                print(
                    f"    {e['game']:<30s} {m.get('label','?'):>5} {m.get('san','?'):<8s} "
                    f"wp={_f(e.get('wp_before')):>7} epl={_f(e.get('epl_lost')):>8} "
                    f"wpG={_f(e.get('wp_gain')):>8} sac={e.get('is_sacrifice','?')} "
                    f"recap={e.get('is_recapture','?')} prev={e.get('prev_classification','?')}"
                )


if __name__ == "__main__":
    main()
