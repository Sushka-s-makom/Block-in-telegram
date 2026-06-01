from __future__ import annotations

import asyncio
import logging
import sqlite3

from telethon import Button, TelegramClient, events
from telethon.errors import PeerIdInvalidError
from telethon.sessions import StringSession
from telethon.tl import types

from app.config import BotSettings, ensure_runtime_dirs, load_bot_settings
from app.core.checker import (
    BlockStatusUndeterminedError,
    check_blocked_via_call,
    check_blocked_via_theme,
    check_blocked_with_fallback,
    resolve_user_id,
)
from app.core.panel_links import build_panel_url
from app.db.storage import get_session, init_db, save_session
from app.logging_utils import configure_logging

logger = logging.getLogger(__name__)
PENDING_STRING_SESSION_INPUT: set[int] = set()
PENDING_CHECK_MODE: dict[int, str] = {}


def build_panel_button(settings: BotSettings, telegram_user_id: int) -> list[list[Button]]:
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


async def create_connected_user_client(settings: BotSettings, bot_user_id: int) -> TelegramClient | None:
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


async def _save_string_session(
    settings: BotSettings,
    bot_user_id: int,
    session_string: str,
) -> tuple[bool, str]:
    client: TelegramClient | None = None

    try:
        client = TelegramClient(StringSession(session_string), settings.api_id, settings.api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            return False, "Эта StringSession не авторизована."

        me = await client.get_me()
        if me is None:
            return False, "Не удалось прочитать владельца StringSession."

        save_session(bot_user_id, me.id, session_string)
        return True, "StringSession сохранена. Теперь можно открыть панель или запустить проверку из чата."
    except Exception:
        logger.exception("failed to save string session sender_id=%s", bot_user_id)
        return False, "Не удалось проверить StringSession. Проверьте, что строка полная и корректная."
    finally:
        if client is not None:
            await client.disconnect()


async def _perform_check(
    settings: BotSettings,
    sender_id: int,
    raw_target: str,
    forwarded_user_id: int | None,
    mode: str,
) -> str:
    client = await create_connected_user_client(settings, sender_id)
    if client is None:
        return "Сначала подключите аккаунт через панель или отправьте StringSession."

    try:
        if forwarded_user_id is not None:
            is_blocked = await run_forward_check(client, forwarded_user_id, mode)
        else:
            is_blocked = await run_check(client, raw_target.strip(), mode)
    except (
        BlockStatusUndeterminedError,
        PeerIdInvalidError,
        TypeError,
        ValueError,
    ):
        logger.exception("check failed sender_id=%s mode=%s target=%r", sender_id, mode, raw_target)
        return "Не удалось определить статус. Проверьте username или попробуйте другой режим."
    finally:
        await client.disconnect()

    return "❌ Пользователь вас заблокировал" if is_blocked else "✅ Пользователь вас не заблокировал"


async def main() -> None:
    configure_logging()
    settings = load_bot_settings()
    ensure_runtime_dirs()
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
                "Для локальной генерации StringSession используйте `python scripts/generate_user_string_session.py`.\n\n"
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
        PENDING_CHECK_MODE.pop(event.sender_id, None)
        await event.respond(
            (
                "Отправьте в этот чат готовую StringSession.\n\n"
                "Бот проверит её через Telethon, сохранит в БД и после этого даст доступ к панели и кнопкам проверок."
            )
        )

    @bot.on(events.CallbackQuery)
    async def on_callback(event: events.CallbackQuery.Event) -> None:
        if event.sender_id is None:
            await event.answer()
            return

        data = event.data.decode("utf-8")

        if data == "info:stringsession":
            await event.answer()
            await event.respond(
                (
                    "StringSession можно получить локально через скрипт "
                    "`python scripts/generate_user_string_session.py`.\n"
                    "После этого отправьте строку командой /session."
                ),
                buttons=build_panel_button(settings, event.sender_id),
            )
            return

        if data == "auth:stringsession":
            PENDING_STRING_SESSION_INPUT.add(event.sender_id)
            PENDING_CHECK_MODE.pop(event.sender_id, None)
            await event.answer()
            await event.respond("Отправьте сюда готовую StringSession одним сообщением.")
            return

        if data.startswith("check:"):
            mode = data.split(":", maxsplit=1)[1]
            PENDING_CHECK_MODE[event.sender_id] = mode
            PENDING_STRING_SESSION_INPUT.discard(event.sender_id)
            await event.answer()
            await event.respond(
                "Отправьте @username, numeric ID или перешлите сообщение пользователя, которого нужно проверить."
            )
            return

        await event.answer()

    @bot.on(events.NewMessage(incoming=True))
    async def on_message(event: events.NewMessage.Event) -> None:
        if not event.is_private or event.sender_id is None:
            return
        if (event.raw_text or "").startswith("/"):
            return

        sender_id = event.sender_id
        if sender_id in PENDING_STRING_SESSION_INPUT:
            PENDING_STRING_SESSION_INPUT.discard(sender_id)
            success, text = await _save_string_session(settings, sender_id, (event.raw_text or "").strip())
            await event.respond(text, buttons=build_panel_button(settings, sender_id if success else sender_id))
            return

        mode = PENDING_CHECK_MODE.pop(sender_id, None)
        if mode is None:
            return

        result_text = await _perform_check(
            settings,
            sender_id,
            event.raw_text or "",
            extract_forwarded_user_id(event),
            mode,
        )
        await event.respond(result_text, buttons=build_panel_button(settings, sender_id))

    try:
        await bot.start(bot_token=settings.bot_token)
        logger.info("bot started successfully")
        print("Bot is running.")
        await bot.disconnected
    finally:
        await bot.disconnect()


def run() -> None:
    try:
        asyncio.run(main())
    except sqlite3.OperationalError as exc:
        if "database is locked" in str(exc).lower():
            raise RuntimeError(
                "A Telethon session database is locked. Stop the other running instance and try again."
            ) from exc
        raise


if __name__ == "__main__":
    run()
