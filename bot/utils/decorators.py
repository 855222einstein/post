"""
Reusable decorators for handler functions.
"""
import functools
from telegram import Update
from telegram.ext import ContextTypes
from bot.config import ADMIN_IDS


def admin_only(func):
    """
    Decorator that restricts a handler to admin users only.

    If ADMIN_IDS is empty, every user is treated as an admin
    (useful during initial setup before any admins are configured).
    """
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return
        if ADMIN_IDS and user.id not in ADMIN_IDS:
            await update.effective_message.reply_text(
                "⛔ You are not authorised to use this command."
            )
            return
        return await func(update, context)

    return wrapper


def private_chat_only(func):
    """Decorator that ensures the handler only runs in private chats."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        if chat and chat.type != "private":
            return  # silently ignore in groups/channels
        return await func(update, context)

    return wrapper
