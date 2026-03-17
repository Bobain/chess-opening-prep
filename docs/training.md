# Training Mode: Find the Better Move

Review your own games, find your mistakes, and drill the correct moves with spaced repetition.

## How it works

```
PREPARATION (your PC, once)              DRILL (browser, daily)
┌─────────────────────────────┐         ┌──────────────────────────────┐
│ chess-self-coach train      │         │ PWA in browser               │
│           --prepare         │  JSON   │                              │
│                             │ ─────→  │ 1. Shows your mistake        │
│ 1. Fetches your games       │         │ 2. "Find a better move"      │
│    (Lichess + chess.com)    │         │ 3. You drag a piece          │
│ 2. Stockfish analyzes each  │         │ 4. Correct → explanation     │
│    position (depth 18)      │         │ 5. Wrong → 3 attempts max    │
│ 3. Finds blunders/mistakes  │         │ 6. Spaced repetition (SM-2)  │
│ 4. Generates explanations   │         │ 7. Progress in localStorage  │
│ 5. Exports training_data.json         │                              │
└─────────────────────────────┘         └──────────────────────────────┘
```

## Quick start

```bash
# 1. Prepare training data
chess-self-coach train --prepare --games 10

# 2. Open the training interface
chess-self-coach train --serve

# 3. Check your stats
chess-self-coach train --stats
```

## Architecture

The training mode has **no backend**. All drill logic runs in the browser:

| Component | Role | Technology |
|-----------|------|------------|
| **Preparation** (CLI) | Fetch games, Stockfish analysis, mistake extraction | Python + python-chess |
| **Board** | Interactive chess board (drag & drop) | [chessground](https://github.com/lichess-org/chessground) (Lichess) |
| **Move validation** | Verify legality, convert to SAN notation | [chess.js](https://github.com/jhlywa/chess.js) |
| **SRS scheduler** | Spaced repetition (SM-2 algorithm) | Vanilla JS |
| **Progress storage** | Persist review state across sessions | localStorage |
| **Offline support** | Cache assets for offline use | Service Worker |

## Mistake categories

| Category | Centipawn loss | Description |
|----------|--------------|-------------|
| **Blunder** | ≥ 200 cp | Hanging a piece, missing mate |
| **Mistake** | 100–199 cp | Missing a tactic, poor exchange |
| **Inaccuracy** | 50–99 cp | Passive move when active was available |

## SM-2 Spaced Repetition

The scheduler uses the SM-2 algorithm (same as Anki):

- **New position**: shown immediately
- **Correct**: interval increases (1d → 3d → 7d → 18d → ...)
- **Wrong**: interval resets to 1 day, ease factor decreases
- **Mastered**: interval > 30 days, position is retired from active review

## Data format

See `training_data.json` for the full schema. Each position contains:

- `fen` — board position
- `player_move` — the mistake the player made
- `best_move` — what Stockfish recommends
- `explanation` — rule-based explanation of why
- `acceptable_moves` — list of moves accepted as correct
- `game` — source game metadata (opponent, date, opening)
