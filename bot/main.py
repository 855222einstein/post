"""
Entry point — initialises and launches the Telegram bot.

Run with:
    python -m bot.main
or from the my-telegram-bot/ directory:
    python -m bot.main
"""
import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from bot.config import BOT_TOKEN
from bot.database.db import init_db

# Handlers
from bot.handlers.start import start_handler, help_handler, privacy_handler
from bot.handlers.admin import (
    myid_handler,
    addchat_handler,
    removechat_handler,
    listchats_handler,
    broadcast_message_handler,
)
from bot.handlers.callbacks import forward_callback, cancel_callback
from bot.handlers.post_creator import build_newpost_handler
from bot.handlers.settings import (
    botsettings_handler,
    usersettings_handler,
    settings_callback,
    settings_input_handler,
    cancel_settings_handler,
)
from bot.modules.auto_forward import channel_post_handler

# ── logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── application setup ─────────────────────────────────────────────────────────

async def _post_init(app: Application) -> None:
    """Async setup that runs inside PTB's managed event loop before polling starts."""
    logger.info("Initialising database…")
    await init_db()
    logger.info("Database ready.")


def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()

    # ── Movie post ConversationHandler (must be first, highest group priority) ──
    app.add_handler(build_newpost_handler(), group=0)

    # ── Group -1: settings input interceptor (highest priority for text) ──
    # Runs before the broadcast handler; only acts when bot is awaiting a value.
    app.add_handler(
        MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, settings_input_handler),
        group=-1,
    )

    # ── Commands ──
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("privacy", privacy_handler))
    app.add_handler(CommandHandler("myid", myid_handler))
    app.add_handler(CommandHandler("addchat", addchat_handler))
    app.add_handler(CommandHandler("removechat", removechat_handler))
    app.add_handler(CommandHandler("listchats", listchats_handler))
    app.add_handler(CommandHandler("botsettings", botsettings_handler))
    app.add_handler(CommandHandler("usersettings", usersettings_handler))
    # /cancel aborts an in-progress Set operation
    app.add_handler(CommandHandler("cancel", cancel_settings_handler))

    # ── Inline-keyboard callbacks ──
    app.add_handler(CallbackQueryHandler(settings_callback, pattern=r"^(bs|us):"))
    app.add_handler(CallbackQueryHandler(forward_callback, pattern=r"^fwd:"))
    app.add_handler(CallbackQueryHandler(cancel_callback, pattern=r"^cancel$"))

    # ── Auto-forward: channel posts from source channel ──
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, channel_post_handler))

    # ── Broadcast: any content sent to the bot in private chat (group 0) ──
    private_content = (
        filters.ChatType.PRIVATE
        & ~filters.COMMAND
        & (
            filters.TEXT
            | filters.PHOTO
            | filters.VIDEO
            | filters.Document.ALL
            | filters.AUDIO
            | filters.VOICE
            | filters.VIDEO_NOTE
            | filters.ANIMATION
            | filters.Sticker.ALL
            | filters.POLL
        )
    )
    app.add_handler(MessageHandler(private_content, broadcast_message_handler))

    return app


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    app = build_application()
    logger.info("Starting bot (long-polling)…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
