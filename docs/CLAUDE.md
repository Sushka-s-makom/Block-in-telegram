# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Telegram bot + FastAPI web panel for detecting whether a Telegram user has blocked you. The bot is the entry point; the web panel handles account connection and block checks. Block detection uses the connected user's own Telegram account (not the bot account) via two techniques: silently setting/reverting a chat theme, or initiating and immediately discarding a phone call.

## Running

Both processes share the same `.env` and `block_checker.db`. They must run simultaneously.

```bash
# Install dependencies
.venv/bin/pip install -r requirements.txt

# Run the Telegram bot
.venv/bin/python -m app.bot

# Run the FastAPI web panel (separate terminal)
.venv/bin/uvicorn app.webapp:app --host 0.0.0.0 --port 8000

# Generate a user StringSession locally (interactive, asks for phone + OTP)
.venv/bin/python scripts/generate_user_string_session.py
```

## Environment variables (`.env`)

Copy `.env.example` to `.env`. Required keys:

| Key | Description |
|-----|-------------|
| `API_ID` / `API_HASH` | From https://my.telegram.org — used by both bot and panel |
| `BOT_TOKEN` | From BotFather |
| `WEB_APP_URL` | Base URL of the FastAPI panel, e.g. `http://127.0.0.1:8000` |
| `APP_SECRET` | Long random string used to HMAC-sign panel links |
| `BOT_STRING_SESSION` | Optional. If set, bot starts from this string session instead of `session/bot` file |
| `PROXY_URL` | Optional SOCKS5/SOCKS4/HTTP proxy, only used in session generator scripts |

## Architecture

### Two-process design

- **`app/bot.py`** — Telethon bot (asyncio). Sends signed panel URLs as inline buttons. Handles multi-step UX via two in-memory dicts: `PENDING_STRING_SESSION_INPUT` (waiting for a pasted StringSession) and `PENDING_CHECK_MODE` (waiting for a check target after the user chose a mode).
- **`app/webapp.py`** — FastAPI panel. Server-renders HTML. Manages the phone→OTP→2FA login flow via the in-memory `PENDING_AUTHS` dict. After successful login it serialises the Telethon session to a StringSession string and stores it in SQLite.

### Shared modules

- **`app/db/storage.py`** — SQLite CRUD over `block_checker.db`. Table `user_sessions` maps `bot_user_id` (Telegram ID of the bot user) to a `StringSession` string. Both processes read/write this table.
- **`app/core/checker.py`** — Core detection logic. `check_blocked_via_theme` is silent (sets then immediately reverts a chat theme, deletes the generated service messages). `check_blocked_via_call` is noticeable (initiates a VoIP call, then discards it and deletes call history). `check_blocked_with_fallback` runs theme first, then call if the theme check returns not-blocked.
- **`app/core/panel_links.py`** — HMAC-SHA256 signed panel URLs with a 1-hour TTL. The bot generates URLs; the panel verifies them on every request via `verify_panel_params`.

### Session management

- The **bot** itself runs from either `session/bot` (file) or `BOT_STRING_SESSION` (env).
- **User accounts** used for checks are stored as StringSessions in SQLite, keyed by the bot user's Telegram ID. The panel can also create temporary file sessions under `session/users/<user_id>` during the login flow before converting them to StringSessions.
- `scripts/generate_bot_string_session.py` / `scripts/generate_user_string_session.py` are one-off helper scripts for generating sessions locally.

### Panel link security

The web panel is accessed via signed links only. `build_panel_url` (called by the bot) embeds `uid`, `exp`, and `sig` query params. Every FastAPI endpoint calls `ensure_access(uid, exp, sig)` which runs `verify_panel_params` and raises HTTP 403 on failure. There is no other authentication mechanism currently.
