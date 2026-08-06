"""
SQLite database connection and models using aiosqlite.

Tables
------
destination_chats
    Stores the list of channels/groups the bot forwards posts to.

forwarded_messages
    Audit log of every forward action.

bot_settings
    Global key-value store for bot-wide configuration.

user_settings
    Per-user key-value store for user preferences.
"""
import os
import aiosqlite
from bot.config import DATABASE_PATH


async def get_connection() -> aiosqlite.Connection:
    """Return an open aiosqlite connection (caller must close it)."""
    os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)
    conn = await aiosqlite.connect(DATABASE_PATH)
    conn.row_factory = aiosqlite.Row
    return conn


async def init_db() -> None:
    """Create tables if they don't exist yet."""
    os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS destination_chats (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     TEXT    NOT NULL UNIQUE,
                title       TEXT    NOT NULL,
                added_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS forwarded_messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                source_chat_id  TEXT NOT NULL,
                source_msg_id   INTEGER NOT NULL,
                dest_chat_id    TEXT NOT NULL,
                forwarded_at    TEXT NOT NULL DEFAULT (datetime('now')),
                status          TEXT NOT NULL DEFAULT 'ok'
            )
            """
        )
        # scope = "bot" for global settings, "user:<user_id>" for per-user settings
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                scope       TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT,
                updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (scope, key)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_posts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                short_id        TEXT    NOT NULL UNIQUE,
                text            TEXT,
                photo_file_id   TEXT,
                sticker_file_id TEXT,
                buttons_raw     TEXT,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        await db.commit()


# ── settings helpers ──────────────────────────────────────────────────────────

async def get_setting(key: str, scope: str = "bot") -> str | None:
    """Return the stored value for (scope, key), or None if not set."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT value FROM settings WHERE scope = ? AND key = ?",
            (scope, key),
        )
        row = await cursor.fetchone()
        return row["value"] if row else None


async def set_setting(key: str, value: str, scope: str = "bot") -> None:
    """Upsert a setting value."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO settings (scope, key, value, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(scope, key) DO UPDATE SET value = excluded.value,
                                                  updated_at = excluded.updated_at
            """,
            (scope, key, value),
        )
        await db.commit()


async def reset_setting(key: str, scope: str = "bot") -> None:
    """Delete a setting so it returns to 'not set'."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM settings WHERE scope = ? AND key = ?",
            (scope, key),
        )
        await db.commit()


# ── destination_chats helpers ─────────────────────────────────────────────────

async def add_destination(chat_id: str, title: str) -> bool:
    """Insert a destination chat. Returns False if it already exists."""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                "INSERT INTO destination_chats (chat_id, title) VALUES (?, ?)",
                (chat_id, title),
            )
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def remove_destination(chat_id: str) -> bool:
    """Delete a destination chat. Returns False if it was not found."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM destination_chats WHERE chat_id = ?", (chat_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def list_destinations() -> list[dict]:
    """Return all destination chats as a list of dicts."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT chat_id, title, added_at FROM destination_chats ORDER BY added_at"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# ── sudo helpers ──────────────────────────────────────────────────────────────

async def get_sudo_ids() -> list[int]:
    """Return the list of user IDs that have sudo (premium) access."""
    raw = await get_setting("sudo", scope="bot")
    if not raw:
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]


async def is_admin_or_sudo(user_id: int) -> bool:
    """Return True if user_id is a configured admin or a sudo user."""
    from bot.config import ADMIN_IDS
    if not ADMIN_IDS or user_id in ADMIN_IDS:
        return True
    return user_id in await get_sudo_ids()


# ── user_posts helpers ────────────────────────────────────────────────────────

async def save_post(
    user_id: int,
    short_id: str,
    text: str | None,
    photo_file_id: str | None,
    sticker_file_id: str | None,
    buttons_raw: str | None,
) -> int:
    """Insert a new user post and return its row id."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO user_posts (user_id, short_id, text, photo_file_id, sticker_file_id, buttons_raw)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, short_id, text or None, photo_file_id, sticker_file_id, buttons_raw or None),
        )
        await db.commit()
        return cursor.lastrowid


async def list_user_posts(user_id: int) -> list[dict]:
    """Return all posts for a given user, newest first."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, short_id, text, created_at FROM user_posts WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def delete_user_post(post_id: int, user_id: int) -> bool:
    """Delete a post by its id, scoped to user_id. Returns True if deleted."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM user_posts WHERE id = ? AND user_id = ?",
            (post_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


# ── forwarded_messages helpers ────────────────────────────────────────────────

async def log_forward(
    source_chat_id: str,
    source_msg_id: int,
    dest_chat_id: str,
    status: str = "ok",
) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO forwarded_messages
                (source_chat_id, source_msg_id, dest_chat_id, status)
            VALUES (?, ?, ?, ?)
            """,
            (source_chat_id, source_msg_id, dest_chat_id, status),
        )
        await db.commit()
