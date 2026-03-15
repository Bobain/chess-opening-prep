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

## 3. Set Up Chessdriller

1. Go to [chessdriller.org](https://chessdriller.org/)
2. Log in with your Lichess account (OAuth — no separate account needed)
3. Chessdriller reads directly from your Lichess Studies

## 4. Install En-Croissant (Optional)

[En-Croissant](https://encroissant.org/) is a desktop chess GUI for visual validation.

1. Download and install from [encroissant.org](https://encroissant.org/)
2. Stockfish 18 is bundled automatically
3. Open PGN files to visually review positions and engine evaluations

!!! warning
    En-Croissant modifies PGN files while they're open. Always **close files** in En-Croissant before running CLI commands.

## 5. Install chess-opening-prep

```bash
# From PyPI
pip install chess-opening-prep

# From source
git clone https://github.com/Bobain/chess-opening-prep.git
cd chess-opening-prep
uv venv && uv sync
```

## 6. Configure

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

## 7. Verify

```bash
chess-opening-prep status
```

This shows the current state of all files, Stockfish, and Lichess configuration.
