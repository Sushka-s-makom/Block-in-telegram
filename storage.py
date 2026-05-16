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

def get_session(bot_user_id: int) -> StoredSession | None:
    with sqlite3.connect(_db_path()) as conn:
        row = conn.execute(
            "select bot_user_id, telegram_user_id, session_string from user_sessions where bot_user_id = ?",
            (bot_user_id,),
        ).fetchone()

    if row is None:
        return None

    return StoredSession(
        bot_user_id=row[0],
        telegram_user_id=row[1],
        session_string=row[2],
    )
def save_session(bot_user_id: int, telegram_user_id: int, session_string: str) -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            insert into user_sessions (bot_user_id, telegram_user_id, session_string)
            values (?, ?, ?)
            on conflict(bot_user_id) do update set
                telegram_user_id = excluded.telegram_user_id,
                session_string = excluded.session_string
            """,
            (bot_user_id, telegram_user_id, session_string),
        )
        conn.commit()


def delete_session(bot_user_id: int) -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute("delete from user_sessions where bot_user_id = ?", (bot_user_id,))
        conn.commit()

