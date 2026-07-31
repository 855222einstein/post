"""Handle /start command and unknown messages."""
from telegram import Update
from telegram.ext import ContextTypes

from bot.db import upsert_user
from bot.keyboards import MAIN_MENU, START_INLINE_KB


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await upsert_user(user.id, user.username, user.first_name)

    await update.message.reply_html(
        f"Hey <b>{user.first_name}</b>! I'm PostBot - I'm here to help you craft "
        "and send posts in one click - just save your templates and send them "
        "instantly! Use /help to find out how to use me to my full potential.\n\n"
        "Join my <a href=\"https://t.me/\">news channel</a> to get information "
        "on all the latest updates.\n\n"
        "Check /privacy to view the privacy policy, and interact with your data.",
        reply_markup=START_INLINE_KB,
        disable_web_page_preview=True,
    )


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(
        "I didn't understand that. Use the keyboard below.",
        reply_markup=MAIN_MENU,
    )
