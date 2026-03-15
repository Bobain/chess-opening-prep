# Setup Guide

## 1. Create a Lichess Account

1. Go to [lichess.org/signup](https://lichess.org/signup)
2. Create a free account

## 2. Create a Lichess API Token

1. Go to [lichess.org/account/oauth/token/create](https://lichess.org/account/oauth/token/create)
2. **Token description**: `chess-opening-prep`
3. Under **STUDIES & BROADCASTS**, check:
    - "Read private studies and broadcasts" (`study:read`)
    - "Create, update, delete studies and broadcasts" (`study:write`)
4. Do **NOT** check any other scopes
5. Click **Submit** — copy the token immediately (shown only once, starts with `lip_`)

### Test your token

```bash
curl -H "Authorization: Bearer lip_your_token" https://lichess.org/api/account
```

## 3. Create Lichess Studies

The CLI cannot create studies via the API (Lichess limitation), so you must create them manually. This is a one-time step.

1. Go to [lichess.org/study](https://lichess.org/study)
2. Click **"+ Create a study"**
3. Set the **Name** to one of these exact names (so the CLI can auto-detect them):
    - `Whites - Queen's Gambit`
    - `Black vs e4 - Scandinavian`
    - `Black vs d4 - Slav`
4. **Visibility**: leave as `Unlisted` (default)
5. Leave all other settings as defaults
6. Click **START**
7. A "New chapter" dialog will appear — **close it** (click ✕). The CLI will create chapters automatically when you push PGN files.
8. Repeat for the other 2 studies

After creating all 3 studies, run `chess-opening-prep setup` to auto-detect them.

## 4. Set Up Chessdriller

1. Go to [chessdriller.org](https://chessdriller.org/)
2. Log in with your Lichess account (OAuth — no separate account needed)
3. Chessdriller reads directly from your Lichess Studies

## 5. Install En-Croissant (Optional)

[En-Croissant](https://encroissant.org/) is a desktop chess GUI for visual validation.

1. Download and install from [encroissant.org](https://encroissant.org/)
2. Stockfish 18 is bundled automatically
3. Open PGN files to visually review positions and engine evaluations

!!! warning
    En-Croissant modifies PGN files while they're open. Always **close files** in En-Croissant before running CLI commands.

## 6. Install chess-opening-prep

```bash
# From PyPI
pip install chess-opening-prep

# From source
git clone https://github.com/Bobain/chess-opening-prep.git
cd chess-opening-prep
uv venv && uv sync
```

## 7. Configure

```bash
# Save your Lichess token
echo "LICHESS_API_TOKEN=lip_your_token_here" > .env

# Run interactive setup
chess-opening-prep setup
```

The `setup` command will:

1. Verify your Lichess authentication
2. Check Stockfish availability
3. List your existing Lichess studies
4. Auto-match studies to PGN files
5. Save the configuration to `config.json`

## 8. Verify

```bash
chess-opening-prep status
```

This shows the current state of all files, Stockfish, and Lichess configuration.
