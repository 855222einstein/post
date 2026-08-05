"""
Centralised configuration — reads from environment / .env file.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Required ──────────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Add it to your .env file.")

# ── Optional ──────────────────────────────────────────────────────────────────
# Comma-separated Telegram user IDs that are allowed to use admin commands.
# If empty, the bot is open to everyone (useful for initial setup).
_raw_admin_ids: str = os.getenv("TELEGRAM_ADMIN_IDS", "")
ADMIN_IDS: list[int] = [
    int(x.strip()) for x in _raw_admin_ids.split(",") if x.strip().isdigit()
]

# Source channel ID.  Posts from this channel are auto-forwarded to all destinations.
SOURCE_CHAT_ID: str = os.getenv("TELEGRAM_SOURCE_CHAT", "")

# SQLite database file path (relative to the project root).
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/bot.db")

# Forward mode: "copy" (no forward tag) or "forward" (shows original source).
FORWARD_MODE: str = os.getenv("FORWARD_MODE", "copy")
