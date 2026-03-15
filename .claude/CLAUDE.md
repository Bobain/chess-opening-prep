# Chess Opening Repertoire

## Player
- Level: ~1000 Elo chess.com rapid (15+10), ~700 estimated FIDE
- Lichess account connected (used with En-Croissant and Chessdriller)
- Target depth: essentials (5-6 moves + common deviations)

## Repertoire
- **White**: Queen's Gambit (1.d4 2.c4) — Harrwitz Attack (5.Bf4) vs QGD
- **Black vs 1.e4**: Modern Scandinavian (1...d5 2.exd5 Nf6) — Fianchetto setup (...g6/...Bg7)
- **Black vs 1.d4**: Slav Defense (1...d5 2...c6) — Czech Variation (...dxc4, ...Bf5 BEFORE e6)
- **Black vs London**: Anti-London with immediate ...c5

## CLI Tool: chess-opening-prep

### Commands
- `chess-opening-prep analyze <file>` — Stockfish analysis with [%eval] annotations
- `chess-opening-prep setup` — Interactive setup (auth, studies, config)
- `chess-opening-prep push <file>` — Push PGN to Lichess study
- `chess-opening-prep pull <file>` — Pull PGN from Lichess study
- `chess-opening-prep status` — Show sync state of all files

### Configuration
- `config.json` — Study IDs, Stockfish path
- `.env` — Lichess API token (gitignored)
- Dependencies: `uv sync`

## PGN Files
Located in `pgn/`. Two versions per opening:
- `*_annote.pgn` — Annotated reference version (comments, variation names, theory markers)
- `*.pgn` — Working copy (may contain En-Croissant Stockfish annotations)

### Structure
- `repertoire_blancs_gambit_dame_annote.pgn` — 6 chapters: QGD (Harrwitz), QGA, Slav (Czech), Nimzo-Indian (Rubinstein), Albin (Lasker Trap), Dutch
- `repertoire_noirs_vs_e4_scandinave_annote.pgn` — 6 chapters: Marshall Fianchetto (4.c4 Nb6), 4.Nf3, 3.Nf3, Icelandic Gambit, 2.e5 (Advance), 2.Nc3/d3
- `repertoire_noirs_vs_d4_slave_annote.pgn` — 5 chapters: Classical Czech, Exchange, Anti-London, Transpositions, Passive moves

## PGN Format
- Each `[Event "Variation name (ECO)"]` = one chapter
- `[Orientation "white"]` or `"black"` = board orientation
- Variations in parentheses `(...)`
- Comments in braces `{...}`
- Stockfish annotations: `{[%eval +0.32]}` (added by En-Croissant or CLI)

## MANDATORY Comment Conventions

### Names and references
- Always use the **official name** of the opening/variation (e.g., "Czech Variation", "Harrwitz Attack")
- Include the **ECO code** when known (e.g., ECO D17, ECO B01)
- Mention **elite players** who use the line (e.g., "played by Carlsen, Kramnik")

### Theoretical status
- Mark **THEORY:** when a move is the theoretical consensus
- Indicate if a line is **modern** or **historical**
- Note when a move is **inferior** or **rare** according to theory
- Flag cases where **in practice** results differ from theory

### Pedagogical explanations
- Explain the **WHY** of each move, not just name it
- Indicate the **plan** after the last move of each line (e.g., "Plan: O-O, Rc1, c-file pressure")
- Flag **traps** with TRAP or WARNING + full explanation
- Mark **TYPICAL MISTAKE** to avoid at the player's level
- Mention **transpositions** when a line joins another

## 3-Zone Workflow

```
Zone 1: Local Files      →  Zone 2: En-Croissant     →  Zone 3: Lichess Study
  (CLI prepares)              + Stockfish 18 local        (source of truth)
  *_annote.pgn                (user validates)            → Chessdriller (drill)
```

### Zone 1 → Zone 2: Preparation → Validation
1. CLI/Claude creates/modifies `*_annote.pgn` files locally
2. ALL comment conventions must be followed
3. Theory verified via web search (variation names, consensus, players)
4. User opens file in En-Croissant
5. Stockfish **18 local** analyzes (NOT Lichess SF16 — more powerful, unlimited time)
6. User adjusts if needed

### Zone 2 → Zone 3: Validation → Publication
1. Once validated: `chess-opening-prep push pgn/<file>.pgn`
2. Lichess Study = **source of truth**

### Zone 3 → Drill
1. Chessdriller connects directly to Lichess studies
2. See `guides/guide_chessdriller.md` for steps
3. Daily drill with spaced repetition

## Anti-Conflict Rules
- **NEVER** write to a file open in En-Croissant → write conflict guaranteed
- Always ask user to **close the file** in En-Croissant before intervention
- En-Croissant modifies PGN continuously (adding evals, reformatting headers)
- `*_annote.pgn` = Claude's workspace, files without suffix = En-Croissant's workspace

## UI Documentation
- Step-by-step UI guides are in `guides/`
- These guides are **evolutionary**: marked `[TO CONFIRM]` until validated by user
- NEVER affirm a UI workflow without user validation
- When guiding the user, ask them to describe what they see to update the guides

## Code Guidelines

Follow the Karpathy principles (see CONTRIBUTING.md):
1. **Think Before Coding** — State assumptions, surface tradeoffs
2. **Simplicity First** — Minimum code, nothing speculative
3. **Surgical Changes** — Touch only what you must
4. **Goal-Driven Execution** — Define success criteria, loop until verified

All code, comments, docstrings, error messages, and logs must be in **English**.
