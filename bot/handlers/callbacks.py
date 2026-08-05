"""
Inline-keyboard callback query handlers.
"""
import re
from telegram import Update
from telegram.ext import ContextTypes
from bot.utils.helpers import forward_message_to_all, build_forward_summary
from bot.database.db import list_destinations


async def forward_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Forward' button press."""
    query = update.callback_query
    await query.answer("Forwarding...")

    match = re.match(r"^fwd:(-?\d+):(\d+)$", query.data or "")
    if not match:
        await query.edit_message_text("Invalid callback data.")
        return

    from_chat_id = int(match.group(1))
    message_id   = int(match.group(2))

    destinations = await list_destinations()
    total = len(destinations)

    success, errors = await forward_message_to_all(
        context.bot, from_chat_id, message_id
    )

    summary = build_forward_summary(success, total, errors)
    await query.edit_message_text(summary)


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Cancel' button press."""
    query = update.callback_query
    await query.answer("Cancelled.")
    await query.edit_message_text("Forwarding cancelled.")
