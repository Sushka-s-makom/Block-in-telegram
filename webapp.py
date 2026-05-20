from __future__ import annotations

import html
import logging
import os
from dataclasses import dataclass
from urllib.parse import quote_plus

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from telethon import TelegramClient
from telethon.errors import (
    PasswordHashInvalidError,
    PeerIdInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberFloodError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
    UserIdInvalidError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.sessions import StringSession

from checker import (
    BlockStatusUndeterminedError,
    check_blocked_via_call,
    check_blocked_via_theme,
    check_blocked_with_fallback,
    resolve_user_id,
)
from panel_links import verify_panel_params
from storage import delete_session, get_session, init_db, save_session

logger = logging.getLogger(__name__)

app = FastAPI()


@dataclass(slots=True)
class Settings:
    api_id: int
    api_hash: str
    app_secret: str
    user_session_dir: str = "session/users"


@dataclass(slots=True)
class PendingAuth:
    client: TelegramClient
    phone: str
    phone_code_hash: str
    stage: str


PENDING_AUTHS: dict[int, PendingAuth] = {}


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def load_settings() -> Settings:
    load_dotenv()

    api_id_raw = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    app_secret = os.getenv("APP_SECRET")

    if not api_id_raw:
        raise RuntimeError("Missing API_ID in environment")
    if not api_hash:
        raise RuntimeError("Missing API_HASH in environment")
    if not app_secret:
        raise RuntimeError("Missing APP_SECRET in environment")

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise RuntimeError("API_ID must be an integer") from exc

    return Settings(api_id=api_id, api_hash=api_hash, app_secret=app_secret)


SETTINGS = load_settings()
configure_logging()
os.makedirs(SETTINGS.user_session_dir, exist_ok=True)
init_db()

def user_session_path(user_id: int) -> str:
    return os.path.join(SETTINGS.user_session_dir, str(user_id))


def panel_url_query(uid: str, exp: str, sig: str) -> str:
    return f"/panel?uid={uid}&exp={exp}&sig={sig}"


def panel_url_with_message(uid: str, exp: str, sig: str, message: str) -> str:
    return f"{panel_url_query(uid, exp, sig)}&msg={quote_plus(message)}"
def ensure_access(uid: str, exp: str, sig: str) -> int:
    if not verify_panel_params(uid, exp, sig, SETTINGS.app_secret):
        raise HTTPException(status_code=403, detail="Invalid or expired panel link")
    return int(uid)


async def create_user_client(user_id: int) -> TelegramClient:
    stored = get_session(user_id)
    session = StringSession(stored.session_string) if stored is not None else user_session_path(user_id)
    client = TelegramClient(session, SETTINGS.api_id, SETTINGS.api_hash)
    await client.connect()
    return client


async def is_connected(user_id: int) -> bool:
    client = await create_user_client(user_id)
    try:
        return await client.is_user_authorized()
    finally:
        await client.disconnect()


async def cleanup_pending_auth(user_id: int) -> None:
    pending = PENDING_AUTHS.pop(user_id, None)
    if pending is not None:
        await pending.client.disconnect()

def render_page(
    uid: str,
    exp: str,
    sig: str,
    *,
    content: str,
    title: str = "Block Checker",
) -> HTMLResponse:
    return HTMLResponse(
        f"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f1ea;
      --card: #fffdf8;
      --text: #1f1a17;
      --muted: #6c625a;
      --accent: #1f6feb;
      --danger: #c0392b;
      --ok: #1e8449;
      --border: #d8cec2;
    }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif;
      background:
        radial-gradient(circle at top left, #ffe8c7 0, transparent 24%),
        radial-gradient(circle at bottom right, #dcecff 0, transparent 26%),
        var(--bg);
      color: var(--text);
    }}
    .wrap {{
      max-width: 760px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 20px;
      box-shadow: 0 16px 40px rgba(31, 26, 23, 0.08);
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 28px;
    }}
    p {{
      color: var(--muted);
      line-height: 1.5;
    }}
    form {{
      display: grid;
      gap: 12px;
      margin-top: 18px;
    }}
    input, button, select {{
      font: inherit;
    }}
    input {{
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: white;
    }}
    button, .button-link {{
      display: inline-block;
      padding: 12px 16px;
      border-radius: 12px;
      border: 0;
      background: var(--accent);
      color: white;
      text-decoration: none;
      cursor: pointer;
      text-align: center;
    }}
    .button-muted {{
      background: #6c625a;
    }}
    .button-danger {{
      background: var(--danger);
    }}
    .grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }}
    .note {{
      margin-top: 14px;
      padding: 12px 14px;
      border-radius: 12px;
      background: #f7f2eb;
      color: var(--text);
    }}
    .ok {{
      color: var(--ok);
      font-weight: 600;
    }}
    .bad {{
      color: var(--danger);
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      {content}
    </div>
  </div>
</body>
</html>
"""
    )