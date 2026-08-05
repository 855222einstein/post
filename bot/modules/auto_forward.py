"""
Auto-forward module — listens for new posts in the configured source channel
and copies them to all destination channels automatically (no confirmation needed).
"""
from telegram import Update
from telegram.ext import ContextTypes
from bot.config import SOURCE_CHAT_ID
from bot.utils.helpers import forward_message_to_all
import logging

logger = logging.getLogger(__name__)


async def channel_post_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Called for every channel_post update.
    Only acts when the post comes from the configured SOURCE_CHAT_ID.
    """
    if not SOURCE_CHAT_ID:
        return

    post = update.channel_post
    if not post:
        return

    if str(post.chat.id) != str(SOURCE_CHAT_ID):
        return

    logger.info(
        "Auto-forwarding message %s from source channel %s",
        post.message_id,
        post.chat.id,
    )

    success, errors = await forward_message_to_all(
        context.bot, post.chat.id, post.message_id
    )

    if errors:
        logger.warning("Auto-forward errors: %s", errors)

    logger.info("Auto-forward complete: %d succeeded", success)
