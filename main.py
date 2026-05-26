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
def build_panel_button(settings: Settings, telegram_user_id: int) -> list[list[Button]]:
    panel_url = build_panel_url(settings.web_app_url, telegram_user_id, settings.app_secret)
    is_connected = get_session(telegram_user_id) is not None
    rows: list[list[Button]] = [[Button.url("Открыть панель", panel_url)]]
    if is_connected:
        rows.append([Button.inline("Тихая проверка", b"check:theme")])
        rows.append([Button.inline("Заметная проверка", b"check:call")])
        rows.append([Button.inline("Тихая + звонок", b"check:combo")])
    rows.append([Button.inline("StringSession", b"info:stringsession")])
    rows.append([Button.inline("Ввести StringSession", b"auth:stringsession")])
    return rows


def extract_forwarded_user_id(event: events.NewMessage.Event) -> int | None:
    forward = event.message.forward
    if forward is None:
        return None
    from_id = getattr(forward, "from_id", None)
    if isinstance(from_id, types.PeerUser) or getattr(from_id, "user_id", None):
        return getattr(from_id, "user_id", None)
    return None