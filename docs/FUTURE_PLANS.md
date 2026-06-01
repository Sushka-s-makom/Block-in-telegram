# Future Plans

## Product Direction

Current state:
- the Telegram bot is only an entry point;
- the web panel handles account connection and block checks;
- this is suitable for local development, not yet for a public multi-user product.

## Next Steps

1. Deploy the web panel to a public domain instead of `127.0.0.1`.
2. Run both processes on a server:
   - Telegram bot
   - FastAPI web panel
3. Replace localhost links with a public `WEB_APP_URL`.
4. Keep per-user Telegram sessions on the server with isolation by Telegram user ID.
5. Add production authentication for the panel:
   - Telegram Mini App or Telegram Login validation
   - signed links as a fallback only
6. Add operational pieces:
   - HTTPS
   - persistent storage / backups for sessions
   - structured logs
   - rate limiting
   - monitoring

## Why This Direction

Telegram login codes sent through Telegram chats are treated as unsafe and may be blocked by Telegram itself.

Because of that, the long-term product architecture should be:
- bot for entry and navigation;
- web panel for account connection and checks;
- server-side session management.

## Session Notes

The bot can now start from `BOT_STRING_SESSION` if needed.

If `BOT_STRING_SESSION` is empty, the app falls back to the file session at `session/bot`.
