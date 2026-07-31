"""PostBot — entry point."""
import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from telegram.error import TelegramError

from bot.db import init_db, migrate_add_columns
from bot.handlers.start import start, unknown
from bot.handlers.profile import profile
from bot.handlers.settings import usersettings, build_settings_handler, btn_close
from bot.handlers.create_post import build_create_post_handler
from bot.handlers.my_posts import (
    show_my_posts,
    view_post,
    paginate_posts,
    send_post,
    ask_delete_post,
    confirm_delete_post,
    cancel_delete,
    show_edit_menu,
    back_to_post,
    build_edit_handler,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _post_init(app: Application) -> None:
    """Called by PTB after the event loop is running — safe place for async init."""
    await init_db()
    await migrate_add_columns()   # add text_pos / buttons_json to existing DBs
    logger.info("Database initialised.")


def build_app(token: str) -> Application:
    app = (
        Application.builder()
        .token(token)
        .post_init(_post_init)
        .build()
    )

    # ── Conversation handlers (must be before plain handlers) ─────────────────
    app.add_handler(build_create_post_handler())
    app.add_handler(build_edit_handler())
    app.add_handler(build_settings_handler())

    # ── Commands ──────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("botsettings", usersettings))

    # ── Main-menu reply-keyboard buttons ─────────────────────────────────────
    app.add_handler(MessageHandler(filters.Regex(r"^📋 My posts$"), show_my_posts))
    app.add_handler(MessageHandler(filters.Regex(r"^👤 Profile$"), profile))

    # ── Inline callback buttons ───────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(paginate_posts, pattern=r"^page:\d+$"))
    app.add_handler(CallbackQueryHandler(view_post, pattern=r"^view:\d+$"))
    app.add_handler(CallbackQueryHandler(send_post, pattern=r"^send:\d+$"))
    app.add_handler(CallbackQueryHandler(ask_delete_post, pattern=r"^delete:\d+$"))
    app.add_handler(CallbackQueryHandler(confirm_delete_post, pattern=r"^confirm_delete:\d+$"))
    app.add_handler(CallbackQueryHandler(cancel_delete, pattern=r"^cancel_delete$"))
    app.add_handler(CallbackQueryHandler(show_edit_menu, pattern=r"^edit:\d+$"))
    app.add_handler(CallbackQueryHandler(back_to_post, pattern=r"^back_to_post:\d+$"))
    app.add_handler(CallbackQueryHandler(btn_close, pattern=r"^us:close$"))

    # ── Fallback ──────────────────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))

    # ── Error handler ─────────────────────────────────────────────────────────
    async def error_handler(update: object, context) -> None:
        if isinstance(context.error, TelegramError):
            logger.warning("TelegramError: %s", context.error)
        else:
            logger.error("Unhandled exception", exc_info=context.error)

    app.add_error_handler(error_handler)

    return app


if __name__ == "__main__":
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN env var is not set")

    logger.info("Bot starting…")
    app = build_app(token)
    # run_polling() manages its own event loop — do NOT wrap in asyncio.run()
    app.run_polling(allowed_updates=Update.ALL_TYPES)
