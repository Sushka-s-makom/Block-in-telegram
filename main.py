from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from dataclasses import dataclass

from dotenv import load_dotenv
from telethon import Button, TelegramClient, events
from telethon.errors import PeerIdInvalidError
from telethon.sessions import StringSession
from telethon.tl import types

from checker import (
    BlockStatusUndeterminedError,
    check_blocked_via_call,
    check_blocked_via_theme,
    check_blocked_with_fallback,
    resolve_user_id,
)
from panel_links import build_panel_url
from storage import get_session, init_db, save_session

logger = logging.getLogger(__name__)
PENDING_STRING_SESSION_INPUT: set[int] = set()
PENDING_CHECK_MODE: dict[int, str] = {}


@dataclass(slots=True)
class Settings:
    api_id: int
    api_hash: str
    bot_token: str
    web_app_url: str
    app_secret: str
    bot_string_session: str | None = None
    bot_session_name: str = "session/bot"


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
