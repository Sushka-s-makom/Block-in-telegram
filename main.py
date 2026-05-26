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
async def create_connected_user_client(settings: Settings, bot_user_id: int) -> TelegramClient | None:
    stored = get_session(bot_user_id)
    if stored is None:
        return None

    client = TelegramClient(StringSession(stored.session_string), settings.api_id, settings.api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return None

    return client


async def run_check(client: TelegramClient, target: str, mode: str) -> bool:
    user_id = await resolve_user_id(client, target)
    if mode == "theme":
        return await check_blocked_via_theme(client, user_id)
    if mode == "call":
        return await check_blocked_via_call(client, user_id)
    return await check_blocked_with_fallback(client, user_id)


async def run_forward_check(client: TelegramClient, user_id: int, mode: str) -> bool:
    if mode == "theme":
        return await check_blocked_via_theme(client, user_id)
    if mode == "call":
        return await check_blocked_via_call(client, user_id)
    return await check_blocked_with_fallback(client, user_id)

async def main() -> None:
    configure_logging()
    settings = load_settings()
    os.makedirs("session", exist_ok=True)
    init_db()

    bot_session = (
        StringSession(settings.bot_string_session)
        if settings.bot_string_session
        else settings.bot_session_name
    )
    bot = TelegramClient(bot_session, settings.api_id, settings.api_hash)

    @bot.on(events.NewMessage(pattern=r"^/(start|menu)$"))
    async def on_start(event: events.NewMessage.Event) -> None:
        if event.sender_id is None:
            return


await event.respond(
            (
                "Откройте панель, подключите свой аккаунт по телефону и коду или вставьте готовую StringSession.\n\n"
                "Для локальной генерации StringSession используйте .venv/bin/python generate_user_string_session.py.\n\n"
                "Тихая проверка: смена темы с откатом.\n"
                "Заметная проверка: короткий звонок с быстрым сбросом."
            ),
            buttons=build_panel_button(settings, event.sender_id),
        )

    @bot.on(events.NewMessage(pattern=r"^/session$"))
    async def on_session_command(event: events.NewMessage.Event) -> None:
        if event.sender_id is None:
            return

        PENDING_STRING_SESSION_INPUT.add(event.sender_id)
        await event.respond(
            (
                "Отправьте в этот чат готовую StringSession.\n\n"
                "Бот проверит её через Telethon, сохранит в БД и после этого даст доступ к панели и кнопкам проверок."
            )
        )
        await event.answer()
    @bot.on(events.NewMessage(incoming=True))
    async def on_message(event: events.NewMessage.Event) -> None:
        if not event.is_private or event.sender_id is None:
            return
        if (event.raw_text or "").startswith("/"):
            return

        if event.sender_id in PENDING_STRING_SESSION_INPUT:
            PENDING_STRING_SESSION_INPUT.discard(event.sender_id)
            session_string = (event.raw_text or "").strip()
            client: TelegramClient | None = None

            try:
                client = TelegramClient(StringSession(session_string), settings.api_id, settings.api_hash)
                await client.connect()
                if not await client.is_user_authorized():
                    await event.respond("Эта StringSession не авторизована.")
                    return

                me = await client.get_me()
                if me is None:
                    await event.respond("Не удалось прочитать владельца StringSession.")
                    return


