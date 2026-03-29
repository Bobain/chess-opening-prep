Analyze classification errors across the full ground truth dataset, find common patterns via parallel chess analysis agents, and derive improved rules for the !! and ! classifier.

**Goal**: maximize macro F1 without overfitting. Rules must be simple and explainable to a 1200 ELO player.

## Step 1: Collect all classification errors

Run the real JS classifier (via Playwright, `window._classifyMove`) on ALL games in `tests/e2e/classification_cases.py` and collect:
- All FN (expected !! or ! but classified as other)
- All FP (classified as !! or ! but expected other)
- For each error: idx, move SAN, cp before→after, is_mate, best move, PV (5 moves), oppEPL, eplLost, wpBefore

Also extract the same data for the move BEFORE and the move AFTER each error (the 3-move context window).

Print a summary: total errors, FN brilliant count, FN great count, FP brilliant count, FP great count.

## Step 2: Deep chess analysis with parallel agents

Launch specialized agents in parallel to analyze the errors. Each agent receives the full 3-move context (move before, the move, move after) with Stockfish eval and best lines.

**Agent grouping** (adapt based on error counts):
- **Agent for FN great**: "Why should these moves be classified as great (!)? What chess characteristic makes them stand out? What quantitative signals could detect them?" Give ALL FN great moves with their 3-move context.
- **Agent for FP great**: "Why are these moves NOT great despite the algorithm flagging them? What distinguishes them from true great moves?" Give ALL FP great moves.
- **Agent for !! errors** (if any): Special attention to brilliant moves — analyze any FN or FP brilliant with detailed context.

Each agent must:
- Use Stockfish eval AND their own chess judgment
- Identify COMMON patterns across moves, not individual explanations
- Propose quantitative criteria that could be implemented in code
- Explicitly flag any rule that would be overfitting

## Step 3: Pattern synthesis

Collect all agent analyses and find convergent themes:
- What patterns do FN great moves share that the current rule misses?
- What patterns do FP great moves share that could filter them out?
- Is the current oppEPL rule salvageable, or should it be replaced/augmented?
- Are there simpler rules that achieve better F1?

## Step 4: Rule derivation

Derive new rules from the synthesis. Requirements:
- **Explainable**: a 1200 ELO player must understand why a move is !/!!
- **General**: rules must apply to chess in general, not our specific games
- **No overfitting**: if a rule only helps on 2-3 specific positions, reject it
- **Quantitative**: rules must use available data (eval, PV, material, oppEPL, eplLost, wpBefore)

Present the proposed rules clearly with:
- The rule in plain language
- The rule in code-like pseudocode
- Expected impact on FN and FP counts
- Any tradeoffs

Ask the user to validate the proposed rules before implementing.

## Step 5: Implementation

After user approval:
1. Update `classifyMove()` in `pwa/app.js`
2. Run `uv run pytest tests/e2e/test_review.py -v` — all tests must pass
3. Print the new macro F1 vs the old one
4. Commit with descriptive message

## Important rules

- NEVER use a Python proxy of the classifier. ALWAYS use `window._classifyMove` via Playwright for error collection.
- **BOTH SIDES**: errors include moves from both players.
- **NO OVERFITTING**: with a larger dataset the risk increases. Every proposed rule must be justified by a general chess principle.
- Pay special attention to !! moves — they are rare and each FN/FP matters more.
- The analysis agents should receive the FULL context: FEN, cp, mate_in, best_move, PV, and the same for the move before and after.
