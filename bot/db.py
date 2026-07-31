"""Database layer using aiosqlite (SQLite)."""
import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "postbot.db")


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_settings (
                user_id     INTEGER PRIMARY KEY,
                log_channel TEXT,    -- channel id/username to forward activity logs
                force_sub   TEXT,    -- @channel users must subscribe to before using bot
                cookies     TEXT,    -- optional cookies string
                updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS posts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                title        TEXT NOT NULL,
                content      TEXT,
                media_type   TEXT,       -- 'photo', 'video', 'document', or NULL (text-only)
                file_id      TEXT,       -- Telegram file_id for media
                caption      TEXT,       -- caption for media posts
                text_pos     TEXT DEFAULT 'below', -- 'below' or 'above' (text relative to media)
                buttons_json TEXT,       -- JSON: [[{text,url},...], ...] rows of inline buttons
                parse_mode   TEXT DEFAULT 'HTML',
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        """)
        await db.commit()


async def upsert_user(user_id: int, username: str | None, first_name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (user_id, username, first_name))
        await db.commit()


async def create_post(
    user_id: int,
    title: str,
    content: str | None = None,
    media_type: str | None = None,
    file_id: str | None = None,
    caption: str | None = None,
    text_pos: str = "below",
    buttons_json: str | None = None,
    parse_mode: str = "HTML",
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO posts (user_id, title, content, media_type, file_id, caption, text_pos, buttons_json, parse_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, title, content, media_type, file_id, caption, text_pos, buttons_json, parse_mode))
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def get_posts(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM posts WHERE user_id = ? ORDER BY created_at DESC
        """, (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_post(post_id: int, user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM posts WHERE id = ? AND user_id = ?
        """, (post_id, user_id)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_post(
    post_id: int,
    user_id: int,
    title: str,
    content: str | None = None,
    media_type: str | None = None,
    file_id: str | None = None,
    caption: str | None = None,
    text_pos: str = "below",
    buttons_json: str | None = None,
) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE posts
            SET title = ?, content = ?, media_type = ?, file_id = ?, caption = ?,
                text_pos = ?, buttons_json = ?
            WHERE id = ? AND user_id = ?
        """, (title, content, media_type, file_id, caption, text_pos, buttons_json, post_id, user_id))
        await db.commit()
        return True


async def get_user_settings(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return {"user_id": user_id, "log_channel": None, "force_sub": None, "cookies": None}


async def set_user_setting(user_id: int, key: str, value: str | None) -> None:
    """Upsert a single setting key for the user."""
    allowed = {"log_channel", "force_sub", "cookies"}
    if key not in allowed:
        raise ValueError(f"Unknown setting key: {key}")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"""
            INSERT INTO user_settings (user_id, {key}, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                {key} = excluded.{key},
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, value))
        await db.commit()


async def migrate_add_columns() -> None:
    """Add new columns to existing DB without data loss."""
    async with aiosqlite.connect(DB_PATH) as db:
        for col, definition in [
            ("text_pos", "TEXT DEFAULT 'below'"),
            ("buttons_json", "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE posts ADD COLUMN {col} {definition}")
                await db.commit()
            except Exception:
                pass  # column already exists


async def delete_post(post_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            DELETE FROM posts WHERE id = ? AND user_id = ?
        """, (post_id, user_id))
        await db.commit()
        return cursor.rowcount > 0


async def get_user_stats(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT u.*, COUNT(p.id) AS post_count
            FROM users u
            LEFT JOIN posts p ON p.user_id = u.user_id
            WHERE u.user_id = ?
            GROUP BY u.user_id
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
