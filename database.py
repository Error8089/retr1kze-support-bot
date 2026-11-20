"""Простое хранилище на SQLite (aiosqlite)."""
import os
from datetime import datetime, timezone

import aiosqlite

from config import DB_PATH


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


async def init_db() -> None:
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                role TEXT NOT NULL DEFAULT 'client',
                pending_chat_id INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                operator_id INTEGER NOT NULL,
                service_key TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                closed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                direction TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                user_id INTEGER,
                chat_id INTEGER,
                service_key TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chats_client ON chats(client_id, status);
            CREATE INDEX IF NOT EXISTS idx_chats_operator ON chats(operator_id, status);
            CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id);
            CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind, created_at);
            """
        )
        await db.commit()


async def register_user(user_id: int, username: str | None, full_name: str | None, role: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users (id, username, full_name, role, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   username = excluded.username,
                   full_name = excluded.full_name,
                   role = excluded.role""",
            (user_id, username or "", full_name or "", role, now()),
        )
        await db.commit()


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return await cursor.fetchone()


async def get_pending(user_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT pending_chat_id FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row and row[0] else None


async def set_pending(user_id: int, chat_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET pending_chat_id = ? WHERE id = ?", (chat_id, user_id))
        await db.commit()


async def clear_pending(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET pending_chat_id = NULL WHERE id = ?", (user_id,))
        await db.commit()


async def create_chat(client_id: int, operator_id: int, service_key: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO chats (client_id, operator_id, service_key, created_at)
               VALUES (?, ?, ?, ?)""",
            (client_id, operator_id, service_key, now()),
        )
        await db.commit()
        return cursor.lastrowid


async def get_chat(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,))
        return await cursor.fetchone()


async def get_active_chat_for_client(client_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM chats WHERE client_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (client_id,),
        )
        return await cursor.fetchone()


async def get_active_chats(operator_id: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if operator_id is None:
            cursor = await db.execute(
                "SELECT * FROM chats WHERE status = 'active' ORDER BY id DESC LIMIT 25"
            )
        else:
            cursor = await db.execute(
                """SELECT * FROM chats WHERE status = 'active' AND operator_id = ?
                   ORDER BY id DESC LIMIT 25""",
                (operator_id,),
            )
        return await cursor.fetchall()


async def close_chat(chat_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE chats SET status = 'closed', closed_at = ? WHERE id = ? AND status = 'active'",
            (now(), chat_id),
        )
        await db.commit()


async def save_message(chat_id: int, sender_id: int, direction: str, body: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO messages (chat_id, sender_id, direction, body, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (chat_id, sender_id, direction, body, now()),
        )
        await db.commit()


async def log(kind: str, user_id: int | None = None, chat_id: int | None = None,
              service_key: str | None = None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO events (kind, user_id, chat_id, service_key, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (kind, user_id, chat_id, service_key, now()),
        )
        await db.commit()


async def get_operator_stats(operator_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async def scalar(sql: str, params=()) -> int:
            cursor = await db.execute(sql, params)
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

        return {
            "chats": await scalar("SELECT COUNT(*) FROM chats WHERE operator_id = ?", (operator_id,)),
            "active": await scalar(
                "SELECT COUNT(*) FROM chats WHERE operator_id = ? AND status = 'active'",
                (operator_id,),
            ),
            "replies": await scalar(
                "SELECT COUNT(*) FROM messages WHERE direction = 'op_to_client' AND sender_id = ?",
                (operator_id,),
            ),
        }


async def get_stats() -> dict:
    day = today()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async def scalar(sql: str, params=()) -> int:
            cursor = await db.execute(sql, params)
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

        stats = {
            "clients": await scalar("SELECT COUNT(*) FROM users WHERE role = 'client'"),
            "clients_today": await scalar(
                "SELECT COUNT(*) FROM users WHERE role = 'client' AND substr(created_at,1,10) = ?", (day,)
            ),
            "chats": await scalar("SELECT COUNT(*) FROM chats"),
            "chats_active": await scalar("SELECT COUNT(*) FROM chats WHERE status = 'active'"),
            "chats_today": await scalar(
                "SELECT COUNT(*) FROM chats WHERE substr(created_at,1,10) = ?", (day,)
            ),
            "messages": await scalar("SELECT COUNT(*) FROM messages"),
            "messages_today": await scalar(
                "SELECT COUNT(*) FROM messages WHERE substr(created_at,1,10) = ?", (day,)
            ),
            "services": await db.execute(
                "SELECT service_key, COUNT(*) AS cnt FROM chats GROUP BY service_key ORDER BY cnt DESC"
            ),
            "operators": await db.execute(
                "SELECT operator_id, COUNT(*) AS cnt FROM chats GROUP BY operator_id ORDER BY cnt DESC"
            ),
            "recent_clients": await db.execute(
                """SELECT u.id, u.username, u.full_name, u.created_at,
                          (SELECT service_key FROM chats c WHERE c.client_id = u.id
                           ORDER BY c.id DESC LIMIT 1) AS last_service
                   FROM users u WHERE u.role = 'client'
                   ORDER BY u.id DESC LIMIT 10"""
            ),
        }
        stats["services"] = await stats["services"].fetchall()
        stats["operators"] = await stats["operators"].fetchall()
        stats["recent_clients"] = await stats["recent_clients"].fetchall()
        return stats
