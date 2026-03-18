# Contributing to chess-self-coach

## Development Setup

```bash
git clone https://github.com/Bobain/chess-self-coach.git
cd chess-self-coach
uv venv && uv sync
chess-self-coach --help
```

## Code Style

- **Language**: All code, comments, docstrings, error messages, and logs in English.
- **Docstrings**: Required on every module, class, and function (Google style).
- **Type hints**: Use `from __future__ import annotations` and type all function signatures.
- **Formatting**: Follow PEP 8. Use `ruff` if available.

## Coding Guidelines

See [`.claude/CLAUDE.md`](.claude/CLAUDE.md) for detailed guidelines:
- **Karpathy Principles** — Think before coding, simplicity first, surgical changes, goal-driven execution
- **E2E Testing** — No silent errors, test with real data, always capture console
- **PGN Conventions** — Comment format for chess opening annotations
