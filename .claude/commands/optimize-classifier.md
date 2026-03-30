Iteratively optimize the !! and ! classifier using fast simulation + parallel worktree validation.

**Goal**: maximize regularized score = macro_F1 - 0.10 * complexity / 50. Rules must be simple and explainable to a 1200 ELO player. NO OVERFITTING.

**Macro F1**: (F1_brilliant + F1_great) / 2, computed globally (aggregate TP/FP/FN across ALL games). F1_other excluded.

**Limits**: max 20 worktree attempts (5 iterations x 4 parallel). Stop early if best score hasn't improved for 2 consecutive iterations.

---

## Step 1: Collect data + BEFORE baseline

Run `/collect-classifier-data` to get `/tmp/classifier_data.json` with enriched features.

Then run the regression test for the BEFORE baseline:
```bash
uv run pytest tests/e2e/test_review.py::test_classification_macro_f1_regression -v -s -n0
```

Record in `/tmp/optimizer_state.md`:
- BEFORE score, macro_f1, complexity breakdown
- Feature statistics summary (key separating features between TP/FP/FN)

## Step 2: Fast simulation — sweep thresholds in Python

**Before generating hypotheses, sweep threshold values using the collector data.**

Read `/tmp/classifier_data.json`. For each tunable threshold in the current classifier, simulate the effect of changing it across a range:

For **oppEpl threshold** (currently 0.15): sweep 0.10, 0.12, 0.14, ..., 0.30. For each value, count how many TP/FP/FN great moves would flip (using the exact `opp_epl` values in the data). Compute simulated F1_great and score.

For **eplLost threshold** (currently 0.02): sweep 0.005, 0.01, 0.015, 0.02, 0.025, 0.03. Same method.

For **brilliant eplLost** (currently -0.005): sweep -0.001, -0.003, -0.005, -0.008, -0.01.

For any **new feature filter** (e.g. `is_check`, `wpBefore > X`): simulate adding it as an AND condition to the existing rules.

**Output**: a table of (threshold_value, simulated_TP, simulated_FP, simulated_FN, simulated_score) for each sweep. Identify the top 5-10 promising configurations.

**Important**: simulation can predict threshold effects accurately (we have exact feature values per move) but CANNOT predict complexity (the test counts complexity from the actual JS code). Assume ±2 complexity uncertainty.

## Step 3: Generate 4 hypotheses

From the simulation results AND accumulated learnings, pick the **4 most promising configurations** to validate in worktrees. Each hypothesis must be a **single, targeted change** (not a combination) in early iterations.

**Categories** (one from each when possible):
1. **Threshold tune**: change an existing numeric threshold to its simulated optimum
2. **New filter**: add a condition using existing features (is_check, wpBefore, etc.)
3. **New helper**: create a new detection function (flat cost: 1 point)
4. **Simplify**: remove a condition to reduce complexity

For each, write in `/tmp/optimizer_state.md`:
- The simulation prediction (TP, FP, FN, estimated score)
- Pseudocode of the exact code change

## Step 4: Parallel worktree validation

Launch **4 Agent calls in a single message** with `isolation: "worktree"`. Each agent receives:

1. **The EXACT current code** of the `classifyMove()` function (copy-paste it from `pwa/app.js` into the prompt — do NOT ask the agent to "find" it)
2. The specific edit to make (line numbers, old code → new code)
3. The test command: `uv run pytest tests/e2e/test_review.py::test_classification_macro_f1_regression -v -s -n0`
4. The expected result format:

```
RESULT:
hypothesis: {one-line description}
score: {regularized score from test output}
macro_f1: {macro F1}
brilliant_tp: {N} brilliant_fp: {N} brilliant_fn: {N} brilliant_f1: {F1}
great_tp: {N} great_fp: {N} great_fn: {N} great_f1: {F1}
complexity: {N} (thresholds: {N}, conditions: {N}, helpers: {N})
status: improved|regressed|error
diff:
{git diff pwa/app.js}
END_RESULT
```

**Critical for reliability**: the agent prompt must include the FULL classifyMove function code and a precise SURGICAL edit instruction (e.g. "on line N, change `>= 0.15` to `>= 0.20`"). Do NOT give vague instructions like "find the great detection and modify it".

## Step 5: Collect results + extract learnings

After all 4 agents complete:

1. Parse RESULT blocks. **Verify scores against simulation predictions** — large discrepancies indicate the simulation model is wrong (e.g. complexity was different than assumed).
2. Record results in `/tmp/optimizer_state.md`
3. Update cumulative learnings (WORKS / DOESN'T WORK / NEUTRAL)
4. **Clean up all worktrees and branches** immediately

## Step 6: Combine winners (later iterations only)

After iteration 1 identifies individual winners, iteration 2+ can test **combinations** of non-conflicting improvements. Only combine changes that individually improved the score.

## Step 7: Iterate or stop

**Stop conditions** (any of):
- 20 total worktree attempts reached
- Best score hasn't improved for 2 consecutive iterations
- All 4 attempts in an iteration returned same or worse score
- Simulation shows no remaining threshold has a better optimum

If continuing: go back to Step 3 with updated learnings. The simulation (Step 2) only runs once.

## Step 8: Apply best result

Once the loop ends:
1. Find the attempt with the highest score across ALL iterations
2. If it improves over BEFORE baseline:
   - Show BEFORE/AFTER comparison table
   - Show the diff
   - Ask the user for validation
   - If approved: apply the diff to `pwa/app.js` on `dev`, run the full test suite (`uv run pytest tests/e2e/test_review.py -v`), commit with BEFORE/AFTER scores in message
3. If no attempt improved: report honestly with summary of what was tried

## Complexity reference

Complexity is computed by `_count_classifier_complexity()` in `tests/e2e/test_review.py`:
- **Zone**: from start of `classifyMove()` to last `return { category: 'brilliant'` or `'great'`
- **Thresholds**: unique numeric constants in comparisons (integers <= 2 excluded). Reusing existing threshold = 0 cost.
- **Conditions**: `if()` with numeric comparisons, function calls, or domain keywords. Null/type guards NOT counted.
- **Helpers**: flat cost 1 point per helper called. Internal complexity NOT counted.
- **Total** = thresholds + conditions + helpers

## Important rules

- All testing in **disposable worktrees** — `dev` is NEVER modified until Step 8
- **Clean up ALL worktrees** after each iteration (git worktree remove + branch delete)
- **Verify `git diff pwa/app.js` is empty** on dev after cleanup — worktree leaks have happened before
- NEVER use a Python proxy of the classifier — the test uses `window._classifyMove` via Playwright
- **BOTH SIDES**: all moves from both players are classified
- **NO OVERFITTING**: every rule must be a general chess principle
- **Single changes first**: early iterations test one change at a time; combinations only after individual effects are measured
