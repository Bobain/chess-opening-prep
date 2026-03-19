# Roadmap

## Legend
- [x] Done — implemented and tested
- [>] Now — being implemented in current batch
- [ ] Later — planned for future implementation

Priority: items are ordered top-to-bottom within each section.
"Next feature" = first `[ ]` item scanning top-to-bottom, across sections.

## 1. Backend Foundation
- [x] FastAPI server with static file serving (no temp dir — serve dynamically)
- [x] `GET /api/status` — mode detection
- [x] `POST /api/stockfish/bestmove` — native Stockfish (with engine crash recovery)
- [x] Stockfish version check at startup
- [x] Port conflict handling (scan 8000-8010)

## 2. PWA Menu & Mode Detection
- [x] Hamburger menu skeleton (top-left)
- [x] Mode detection via /api/status
- [x] Hide demo banner in [app] mode
- [x] "Stockfish is thinking" indicator (both modes)
- [x] Native Stockfish API for opponent response in [app] mode (with WASM fallback)
- [x] Analysis depth setting: default 18 [app], 12 [demo] — configurable in Settings

## 3. Training Pipeline (CLI → PWA)
- [ ] `POST /api/train/prepare` — trigger training data generation from menu
- [ ] `GET /api/train/progress` — SSE progress stream (real-time feedback)
- [ ] `POST /api/games/import` — import games from Lichess/chess.com

## 4. Settings & Setup
- [ ] Settings sync API — localStorage ↔ backend config.json
- [ ] Move settings into hamburger menu (replace gear icon)
- [ ] Edit config from PWA (modify usernames, token, SF path set at install)
- [ ] Display Stockfish version in About/Status

Note: `chess-self-coach setup` runs at install time (one-liner).
Config.json exists before the PWA is ever launched.
PWA Settings = modify existing config, not initial setup.

## 5. Chess Prep — Repertoire Tools (CLI → PWA)
- [ ] Sync status dashboard (which files are synced, modified, etc.)
- [ ] Pull PGN from Lichess Study (menu item)
- [ ] Push PGN to Lichess Study (menu item)
- [ ] Analyze PGN with Stockfish (menu item)
- [ ] Validate PGN annotations (menu item)
- [ ] Cleanup empty Lichess study chapters

## 6. Chess Prep — Coaching & Study
- [ ] Coaching journal viewer (browse coaching/topics/ in PWA)
- [ ] PGN viewer/editor in PWA (visualize repertoire files)
- [ ] Repertoire explorer (interactive tree of lines)
- [ ] Opening quiz mode (drill repertoire lines, not just mistakes)
