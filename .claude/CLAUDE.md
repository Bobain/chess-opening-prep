# Chess Self-Coach

## Code Guidelines

All code, comments, docstrings, error messages, and logs must be in **English**.

### Karpathy Principles

Behavioral guidelines to reduce common LLM coding mistakes, derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876). These bias toward caution over speed — for trivial tasks, use judgment.

#### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

#### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

#### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

#### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

### Code Style

- **Docstrings**: Required on every module, class, and function (Google style).
- **Type hints**: Use `from __future__ import annotations` and type all function signatures.
- **Formatting**: Follow PEP 8. Use `ruff` if available.

---

## E2E Testing & Silent Errors

Rules learned from debugging the "See moves" link (hours lost to silent failures and fake-passing tests).

### No Silent Errors — EVER

- **JavaScript**: NEVER use `if (el)` guards that silently skip logic. If `getElementById` returns null, it's a bug — throw an explicit error or `console.error()` so it's visible.
- **Python**: NEVER use bare `except: pass`. Always log or re-raise.
- **General**: A function that fails silently is worse than one that crashes. Crashes are debuggable; silent failures waste hours.

### E2E Tests Must Use Real Data

- **NEVER test only with simplified fixtures**. Always include at least one test that runs against the real `training_data.json` (the production data).
- Fixtures are useful for unit-like e2e tests (known positions, predictable moves). But a separate "production smoke test" must verify the real data path.
- The "See moves" bug passed all fixture tests but failed in production because fixtures were missing `game.id` fields.

### Playwright Tests: Always Capture Console

- The `console_errors` fixture in `tests/e2e/conftest.py` is `autouse=True` — it automatically captures all browser console messages and JS errors for every test.
- Tests fail automatically if any JS error is detected.
- All console output is printed in pytest `-v` output for debugging.
- NEVER run Playwright tests without console capture. If writing a standalone debug script, always attach `page.on('console')` and `page.on('pageerror')` listeners.
- Use `console_errors["messages"]` in assertions to verify that specific JS code paths were executed (e.g., `assert "[showFeedback]" in log_text`).

### JavaScript: Always Add Console Logs in Key Functions

- Every user-facing function (`showFeedback`, `handleMove`, `showPosition`, etc.) MUST have `console.log` at entry with its key parameters.
- Every branch (correct/wrong/error) MUST log which path was taken.
- Every DOM lookup that could fail MUST log whether the element was found or null.
- These logs are essential for debugging in the browser console — without them, failures are invisible.
- This is NOT optional debug code to remove later. It stays permanently.

### Playwright: Annotated Screenshots for UI Communication

- When showing a UI element to the user, **generate an annotated screenshot** with Playwright instead of describing it in text.
- Technique: `page.evaluate()` injects a canvas overlay, draws a red arrow pointing to the element, then `page.screenshot()` captures the result.
- Use `page.locator('#element').bounding_box()` to get the element's position for the arrow.
- Save to `~/Screenshots/` and read the file to show the user.
- This avoids miscommunication ("where is it?") and saves debugging time.

### Service Worker: Network-First for Local Assets

- The PWA service worker MUST use **network-first** for same-origin assets (always serve fresh files from server, cache as offline fallback).
- **Cache-first** is only for CDN resources (which never change).
- `serve_pwa()` creates a temp dir on each launch — the SW must fetch fresh files, not serve stale cache.
- Lesson: `skipWaiting()` + `clients.claim()` are NOT enough to invalidate cache-first responses from the old SW's fetch handler.

---

## Chess Context

### Player
- Level: ~1000 Elo chess.com rapid (15+10), ~700 estimated FIDE
- Lichess: [bobainbobain](https://lichess.org/@/bobainbobain)
- Chess.com: [Tonigor1982](https://www.chess.com/member/Tonigor1982)
- Target depth: essentials (5-6 moves + common deviations)

### Lichess Studies
- [Whites - Queen's Gambit](https://lichess.org/study/ucjmuish)
- [Black vs e4 - Scandinavian](https://lichess.org/study/IoJ5waZo)
- [Black vs d4 - Slav](https://lichess.org/study/x3z4bEQ6)

### Repertoire
- **White**: Queen's Gambit (1.d4 2.c4) — Harrwitz Attack (5.Bf4) vs QGD
- **Black vs 1.e4**: Modern Scandinavian (1...d5 2.exd5 Nf6) — Fianchetto setup (...g6/...Bg7)
- **Black vs 1.d4**: Slav Defense (1...d5 2...c6) — Czech Variation (...dxc4, ...Bf5 BEFORE e6)
- **Black vs London**: Anti-London with immediate ...c5

### PGN Files
Located in `pgn/`. Two versions per opening:
- `*_annote.pgn` — Annotated reference version (comments, variation names, theory markers)
- `*.pgn` — Working copy (may contain Stockfish annotations)

### PGN Format
- Each `[Event "Variation name (ECO)"]` = one chapter
- `[Orientation "white"]` or `"black"` = board orientation
- Variations in parentheses `(...)`
- Comments in braces `{...}`
- Stockfish annotations: `{[%eval +0.32]}` (added by CLI or Lichess)

### MANDATORY Comment Conventions

#### Names and references
- Always use the **official name** of the opening/variation (e.g., "Czech Variation", "Harrwitz Attack")
- Include the **ECO code** when known (e.g., ECO D17, ECO B01)
- Mention **elite players** who use the line (e.g., "played by Carlsen, Kramnik")

#### Theoretical status
- Mark **THEORY:** when a move is the theoretical consensus
- Indicate if a line is **modern** or **historical**
- Note when a move is **inferior** or **rare** according to theory
- Flag cases where **in practice** results differ from theory

#### Pedagogical explanations
- Explain the **WHY** of each move, not just name it
- Indicate the **plan** after the last move of each line (e.g., "Plan: O-O, Rc1, c-file pressure")
- Flag **traps** with TRAP or WARNING + full explanation
- Mark **TYPICAL MISTAKE** to avoid at the player's level
- Mention **transpositions** when a line joins another

### 2-Zone Workflow

```
Zone 1: Local Files      →  Zone 2: Lichess Study
  (CLI prepares + analyzes)    (source of truth + interactive study)
  *_annote.pgn                 → Chessdriller (drill)
```

#### Zone 1 → Zone 2: Preparation → Publication
1. CLI/Claude creates/modifies `*_annote.pgn` files locally
2. ALL comment conventions must be followed
3. Theory verified via web search (variation names, consensus, players)
4. `chess-self-coach validate` to check annotations
5. `chess-self-coach analyze` for Stockfish validation
6. `chess-self-coach push` to publish to Lichess Study

#### Zone 2: Interactive study
1. Lichess Study = **source of truth**
2. User studies interactively on Lichess (play moves, engine analysis)
3. `chess-self-coach pull` to sync changes back to local

#### Optional: En-Croissant
En-Croissant is a desktop chess GUI for offline visual review of PGN files.
Not required — Lichess Study provides the same functionality online.
If used: **NEVER** write to a file open in En-Croissant → write conflict guaranteed.

### Coaching Journal (MANDATORY)

After EVERY chess theory discussion (Q&A about openings, style, move choices, repertoire decisions):
1. Create or update a topic file in `coaching/topics/YYYY-MM-DD-slug.md`
2. Update `coaching/INDEX.md` with the new entry (categorized by opening)
3. This is **AUTOMATIC** — do NOT wait for the user to ask

### UI Documentation
- Step-by-step UI guides are in `guides/`
- These guides are **evolutionary**: marked `[TO CONFIRM]` until validated by user
- NEVER affirm a UI workflow without user validation
