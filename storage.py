from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass


@dataclass(slots=True)
class StoredSession:
    bot_user_id: int
    telegram_user_id: int
    session_string: str


def _db_path() -> str:
    return os.path.join(os.getcwd(), "block_checker.db")


def init_db() -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            create table if not exists user_sessions (
                bot_user_id integer primary key,
                telegram_user_id integer not null,
                session_string text not null
            )
            """
        )
        conn.commit()



