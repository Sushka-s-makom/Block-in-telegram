from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    load_dotenv()

    api_id_raw = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    bot_token = os.getenv("BOT_TOKEN")

    if not api_id_raw:
        raise RuntimeError("Missing API_ID in environment")
    if not api_hash:
        raise RuntimeError("Missing API_HASH in environment")
    if not bot_token:
        raise RuntimeError("Missing BOT_TOKEN in environment")

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise RuntimeError("API_ID must be an integer") from exc

    client = TelegramClient(StringSession(), api_id, api_hash)
    try:
        await client.start(bot_token=bot_token)
        print(client.session.save())
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
