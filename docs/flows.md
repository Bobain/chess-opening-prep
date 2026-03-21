# Flows

This page documents how data and actions flow through the system — from the user's perspective, through the backend, and into storage.

## 1. Training session (PWA)

The core user-facing flow: the player practices positions extracted from their own games.

```mermaid
sequenceDiagram
    participant U as Player
    participant PWA as Browser (PWA)
    participant LS as localStorage
    participant SF as Stockfish WASM

    PWA->>PWA: Load training_data.json
    PWA->>LS: Load SRS state (train_srs)
    PWA->>PWA: selectPositions(positions, count)<br/>Priority: overdue → new → learning
    loop Each position
        PWA->>U: Show board + context prompt
        U->>PWA: Make a move
        alt Correct move
            PWA->>U: ✓ Feedback + explanation
            PWA->>LS: updateSRS(correct=true)
        else Wrong move
            PWA->>U: "Not quite. Try again."
            PWA->>SF: getStockfishBestMove(fen)
            SF-->>PWA: Opponent response (UCI)
            PWA->>U: Animate opponent move + Retry button
            Note over U,PWA: Player can retry<br/>unlimited times or<br/>click "Give up"
        end
        U->>PWA: Click Next
    end
    PWA->>U: Session summary (X/Y correct)
```

### Key details

- **Position selection** uses SM-2 spaced repetition: overdue positions first, then new (blunders prioritized), then learning (interval < 7 days). Mastered positions are skipped.
- **Intra-session repetition**: a correct first attempt reinserts the position 5 slots later for confirmation. A wrong answer reinserts 3 slots later.
- **Dismiss** ("Give up on this lesson") sets interval to 99999 days — the position never appears again.
- **SRS state** is stored per position ID in `localStorage` key `train_srs`.

---

## 2. Analyse latest games (app mode)

Fetches recent games, runs Stockfish analysis, and generates training positions.

```mermaid
sequenceDiagram
    participant U as Player
    participant PWA as Browser
    participant API as FastAPI server
    participant W as Worker threads
    participant SF as Stockfish (native)
    participant L as Lichess API
    participant C as Chess.com API

    U->>PWA: Click "Analyse latest games"
    PWA->>API: POST /api/train/prepare
    API-->>PWA: 202 + job_id
    PWA->>API: GET /api/jobs/{id}/events (SSE)

    API->>API: Load existing training_data.json<br/>(preserve SRS + analyzed_game_ids)

    par Fetch games
        API->>L: Fetch ≤20 recent rated games
        API->>C: Fetch ≤20 recent rated games
    end

    API->>API: Filter: skip already-analyzed games

    loop Each new game (parallel workers)
        API->>W: Analyze game
        W->>SF: depth-18 analysis per position
        SF-->>W: eval scores
        W-->>API: Positions with cp_loss > threshold
        API-->>PWA: SSE: analyze phase (X/Y, percent)
        API->>API: Atomic write to training_data.json
    end

    API-->>PWA: SSE: done (summary)
    PWA->>PWA: Reload training_data.json
    PWA->>PWA: Restart session
```

### Key details

- **Incremental merge**: only new games are analyzed. Existing positions keep their SRS state.
- **Thresholds**: blunder ≥ 200cp, mistake ≥ 100cp, inaccuracy ≥ 50cp.
- **Parallelism**: N-1 CPU cores (ProcessPoolExecutor).
- **Crash safety**: atomic write after each game — if interrupted, partial results are saved.
- **Interrupt**: user can click the interrupt button → `POST /api/jobs/{id}/cancel` → saves progress so far.
- **Hardcoded defaults** (v0.3.8): 20 games per source, depth 18, no UI to customize.

---

## 3. Data lifecycle

How training data flows from chess platforms to the player's practice sessions.

```mermaid
flowchart LR
    subgraph Sources
        LI[Lichess API]
        CC[Chess.com API]
    end

    subgraph Backend
        IMP[Importer<br/>fetch games]
        SF[Stockfish 18<br/>analyze positions]
        TR[Trainer<br/>extract mistakes]
    end

    subgraph Storage
        TD[training_data.json<br/>positions + game metadata]
        LS[localStorage<br/>SRS state per position]
    end

    subgraph PWA
        SEL[Session selector<br/>SM-2 priority]
        QUIZ[Quiz interface<br/>board + feedback]
    end

    LI --> IMP
    CC --> IMP
    IMP --> SF
    SF --> TR
    TR --> TD
    TD --> SEL
    LS --> SEL
    SEL --> QUIZ
    QUIZ --> LS
```

### training_data.json structure

```
{
  version, generated, player: {lichess, chesscom},
  positions: [
    { id, fen, player_color, player_move, best_move,
      context, score_before, score_after, cp_loss, category,
      explanation, acceptable_moves, pv,
      game: { id, source, opponent, date, result },
      clock: { player, opponent },
      srs: { interval, ease, next_review, history } }
  ],
  analyzed_game_ids: [...]
}
```

### localStorage SRS state

```
train_srs: {
  "<position_id>": {
    interval, ease, repetitions, next_review,
    history: [{ date, correct, dismissed? }]
  }
}
```

---

## 4. SRS (Spaced Repetition) algorithm

The SM-2 variant used for scheduling position reviews.

```mermaid
stateDiagram-v2
    [*] --> New: Position created
    New --> Learning: First review (interval=1d)
    Learning --> Learning: Wrong (interval=1d, ease↓)
    Learning --> Learning: Correct (interval×ease)
    Learning --> Mastered: interval ≥ 7d
    Mastered --> Learning: Overdue + wrong
    New --> Dismissed: "Give up"
    Learning --> Dismissed: "Give up"
    Dismissed --> [*]: interval=99999d<br/>Never shown again
```

| Outcome | Effect |
|---------|--------|
| Correct (1st rep) | interval = 1 day |
| Correct (2nd rep) | interval = 3 days |
| Correct (3rd+ rep) | interval = interval × ease |
| Wrong | interval = 1 day, repetitions = 0 |
| Ease adjustment | ease += 0.1 − (5−q)(0.08 + (5−q)×0.02), min 1.3 |

---

## 5. CI/CD pipeline

What happens when code is pushed.

```mermaid
flowchart TD
    subgraph "Push to main"
        PUSH[git push origin main]
    end

    subgraph "CI: Test (deploy.yml)"
        UT[Unit tests<br/>pytest tests/ --ignore=e2e]
        E2E[E2E tests<br/>pytest tests/e2e/<br/>Playwright + Chromium]
        UT --> E2E
    end

    subgraph "CD: Deploy (deploy.yml)"
        JSDOC[Generate JS API docs<br/>jsdoc-to-markdown pwa/app.js]
        MKDOCS[Build MkDocs site<br/>mkdocs build]
        VER[Inject version into SW<br/>sed pyproject.toml → sw.js]
        ASM[Assemble site:<br/>landing + docs + PWA]
        GHP[Deploy to GitHub Pages]
        JSDOC --> MKDOCS --> VER --> ASM --> GHP
    end

    subgraph "Release (publish.yml)"
        TAG[Create GitHub Release]
        PYPI[Build + publish to PyPI<br/>uv build + trusted publishing]
        TAG --> PYPI
    end

    PUSH --> UT
    E2E --> JSDOC
    TAG -.-> |manual trigger| PYPI

    subgraph "CI: PR (ci.yml)"
        PRUT[Unit tests]
        PRE2E[E2E tests]
        PRUT --> PRE2E
    end
```

### GitHub Pages site structure

```
site/
├── index.html          ← Landing page
├── docs/               ← MkDocs output (this documentation)
│   ├── index.html
│   ├── setup/
│   ├── cli/
│   ├── training/
│   ├── flows/
│   └── api/
└── train/              ← PWA (demo mode)
    ├── index.html
    ├── app.js
    ├── style.css
    ├── sw.js
    ├── manifest.json
    ├── training_data.json
    └── stockfish/
```

---

## 6. PWA mode detection

How the app decides whether it's running as a demo or as an installed application.

```mermaid
flowchart TD
    START[PWA loads] --> FETCH[Fetch /api/status]
    FETCH -->|200 OK| APP[App mode]
    FETCH -->|Network error / 404| DEMO[Demo mode]

    APP --> SHOW[Show app-only menu items<br/>Enable native Stockfish<br/>Set depth=18]
    DEMO --> HIDE[Hide app-only items<br/>Use WASM Stockfish<br/>Set depth=12]

    APP --> VER{Version check}
    VER -->|Newer available| PROMPT[Show update prompt]
    VER -->|Up to date| READY[Ready]
    DEMO --> READY
```

---

## 7. Service worker & caching

How the PWA handles offline access and updates.

```mermaid
flowchart TD
    REQ[Browser request] --> SW[Service Worker]
    SW --> ORIGIN{Same origin?}

    ORIGIN -->|Yes| NF[Network first<br/>Try server → fallback to cache]
    ORIGIN -->|No CDN| CF[Cache first<br/>Try cache → fallback to network]

    NF -->|Success| CACHE1[Update cache + serve]
    NF -->|Offline| SERVE1[Serve from cache]

    CF -->|Cache hit| SERVE2[Serve from cache]
    CF -->|Cache miss| FETCH2[Fetch + cache + serve]
```

### Key rules

- **Network-first** for same-origin assets: always serve fresh files from the server (important because `server.py` serves files dynamically).
- **Cache-first** for CDN resources (chessground, chess.js): these never change.
- `skipWaiting()` + `clients.claim()` ensure the new SW takes over immediately.
