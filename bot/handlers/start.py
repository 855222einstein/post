"""
/start, /help, and /privacy command handlers.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.utils.decorators import private_chat_only
from bot.database.db import get_setting

import re


def _escape_md(text: str) -> str:
    """Escape special chars for MarkdownV2."""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', text)


def _build_welcome_text(news_url: str | None) -> str:
    if news_url:
        # Normalise @username → URL
        if news_url.startswith("@"):
            news_url = f"https://t.me/{news_url[1:]}"
        elif not news_url.startswith("http"):
            news_url = f"https://t.me/{news_url}"
        channel_part = f"Join my [news channel]({news_url}) to get information on all the latest updates\\."
    else:
        channel_part = "Join my news channel to get information on all the latest updates\\."

    return (
        "Hey there\\! My name is *Himawari Nohara* \\- I'm here to help you manage your groups\\! "
        "Use /help to find out how to use me to my full potential\\.\n\n"
        f"{channel_part}\n\n"
        "Check /privacy to view the privacy policy, and interact with your data\\."
    )


HELP_TEXT = """
*Post Forward Bot — Help*

*How to use:*
1\\. Add destination channels with /addchat
2\\. Make sure I'm an admin in those channels
3\\. Send any post to me — I'll ask you to confirm before forwarding

*Commands:*
/addchat `<chat_id>` — add a destination channel
/removechat `<chat_id>` — remove a destination channel
/listchats — view all destinations
/myid — get your Telegram user ID
/privacy — view privacy policy
/help — show this message

*Tip:* Get a channel's ID by forwarding a message from it to @userinfobot
""".strip()

PRIVACY_TEXT = (
    "*Privacy Policy*\n\n"
    "This bot stores only the following data:\n"
    "• Destination channel IDs and titles you configure\n"
    "• A log of forwarded messages \\(source chat, message ID, destination, timestamp\\)\n\n"
    "No personal messages, usernames, or contact data are stored\\.\n\n"
    "To request data deletion, contact the bot administrator\\."
)


def _start_keyboard(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    deep_link = f"https://t.me/{bot_username}?start={user_id}"
    share_url  = f"https://t.me/share/url?url={deep_link}"
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("sʜᴀʀᴇ", url=share_url)]]
    )


@private_chat_only
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    news_url = await get_setting("news_channel", scope="bot")
    welcome_text = _build_welcome_text(news_url)
    bot_username = (await context.bot.get_me()).username
    user_id = update.effective_user.id
    await update.message.reply_text(
        welcome_text,
        parse_mode="MarkdownV2",
        reply_markup=_start_keyboard(bot_username, user_id),
        disable_web_page_preview=True,
    )


@private_chat_only
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode="MarkdownV2")


@private_chat_only
async def privacy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(PRIVACY_TEXT, parse_mode="MarkdownV2")
