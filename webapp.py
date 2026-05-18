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