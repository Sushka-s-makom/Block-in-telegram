from __future__ import annotations

import asyncio
import logging
import os

from telethon import TelegramClient, functions, types
from telethon.errors import PeerIdInvalidError, RPCError, UserIsBlockedError

logger = logging.getLogger(__name__)


class BlockStatusUndeterminedError(RuntimeError):
    """Raised when Telegram does not expose a reliable block status."""


def _extract_message_ids_from_updates(result: object) -> list[int]:
    message_ids: list[int] = []

    messages = getattr(result, "messages", None) or []
    for message in messages:
        message_id = getattr(message, "id", None)
        if isinstance(message_id, int):
            message_ids.append(message_id)

    updates = getattr(result, "updates", None) or []
    for update in updates:
        update_message = getattr(update, "message", None)
        update_message_id = getattr(update_message, "id", None)
        if isinstance(update_message_id, int):
            message_ids.append(update_message_id)
            continue

        direct_message_id = getattr(update, "message_id", None)
        if isinstance(direct_message_id, int):
            message_ids.append(direct_message_id)

    return list(dict.fromkeys(message_ids))


async def _delete_service_messages(client: TelegramClient, peer: int, result: object) -> None:
    message_ids = _extract_message_ids_from_updates(result)
    if not message_ids:
        return

    try:
        await client.delete_messages(entity=peer, message_ids=message_ids, revoke=True)
        logger.info("_delete_service_messages: peer=%s message_ids=%s", peer, message_ids)
    except RPCError as exc:
        logger.warning(
            "_delete_service_messages: failed peer=%s message_ids=%s error=%s",
            peer,
            message_ids,
            exc,
        )


async def _delete_recent_phone_call_messages(client: TelegramClient, peer: int, call_id: int) -> None:
    await asyncio.sleep(0.6)

    message_ids: list[int] = []
    async for message in client.iter_messages(peer, limit=10):
        action = getattr(message, "action", None)
        if isinstance(action, types.MessageActionPhoneCall) and action.call_id == call_id:
            message_ids.append(message.id)

    if not message_ids:
        return

    try:
        await client.delete_messages(entity=peer, message_ids=message_ids, revoke=True)
        logger.info(
            "_delete_recent_phone_call_messages: peer=%s call_id=%s message_ids=%s",
            peer,
            call_id,
            message_ids,
        )
    except RPCError as exc:
        logger.warning(
            "_delete_recent_phone_call_messages: failed peer=%s call_id=%s error=%s",
            peer,
            call_id,
            exc,
        )
async def resolve_user_id(client: TelegramClient, raw_target: str) -> int:
    target = raw_target.strip()
    if not target:
        raise ValueError("Target is empty")

    if target.startswith("@"):
        entity = await client.get_entity(target)
    else:
        try:
            entity = await client.get_entity(int(target))
        except ValueError:
            entity = await client.get_entity(target)

    if not isinstance(entity, types.User):
        raise TypeError("Target is not a user")
    if entity.bot:
        raise TypeError("Target is a bot")

    return entity.id

async def _get_current_chat_theme(client: TelegramClient, user_id: int) -> types.TypeInputChatTheme:
    full = await client(functions.users.GetFullUserRequest(id=user_id))
    current_theme = getattr(full.full_user, "theme", None)
    current_emoticon = getattr(current_theme, "emoticon", None)
    if current_emoticon:
        return types.InputChatTheme(emoticon=current_emoticon)
    return types.InputChatThemeEmpty()


async def _pick_probe_chat_theme(
    client: TelegramClient,
    current_emoticon: str | None,
) -> types.InputChatTheme:
    chat_themes = await client(functions.account.GetChatThemesRequest(hash=0))
    chat_items = getattr(chat_themes, "themes", [])

    for theme in chat_items:
        if isinstance(theme, types.ChatTheme) and theme.emoticon and theme.emoticon != current_emoticon:
            return types.InputChatTheme(emoticon=theme.emoticon)
        if isinstance(theme, types.Theme) and theme.emoticon and theme.emoticon != current_emoticon:
            return types.InputChatTheme(emoticon=theme.emoticon)

    themes = await client(functions.account.GetThemesRequest(format="android", hash=0))
    items = getattr(themes, "themes", [])
    for theme in items:
        if isinstance(theme, types.Theme) and theme.for_chat and theme.emoticon and theme.emoticon != current_emoticon:
            return types.InputChatTheme(emoticon=theme.emoticon)

    raise BlockStatusUndeterminedError("No alternative chat theme found")


async def check_blocked_via_theme(client: TelegramClient, user_id: int) -> bool:
    original_theme = await _get_current_chat_theme(client, user_id)
    current_emoticon = getattr(original_theme, "emoticon", None)
    probe_theme = await _pick_probe_chat_theme(client, current_emoticon)

    try:
        result = await client(
            functions.messages.SetChatThemeRequest(
                peer=user_id,
                theme=probe_theme,
            )
        )
    except UserIsBlockedError:
        return True
    except PeerIdInvalidError:
        return True
    except RPCError as exc:
        raise BlockStatusUndeterminedError(str(exc)) from exc

    try:
        revert_result = await client(
            functions.messages.SetChatThemeRequest(
                peer=user_id,
                theme=original_theme,
            )
        )
        await _delete_service_messages(client, user_id, result)
        await _delete_service_messages(client, user_id, revert_result)
    except RPCError as exc:
        raise BlockStatusUndeterminedError(str(exc)) from exc

    return False


