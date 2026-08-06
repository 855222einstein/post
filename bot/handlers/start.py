"""
/start, /help, and /privacy command handlers.

All three views live in the SAME message bubble:
  /start  → welcome text  + [sʜᴀʀᴇ] [ʜᴇʟᴘ] [ᴘʀɪᴠᴀᴄʏ]
  ʜᴇʟᴘ   → help text     + [ʙᴀᴄᴋ]
  ᴘʀɪᴠᴀᴄʏ→ privacy text  + [ʙᴀᴄᴋ]
  ʙᴀᴄᴋ   → welcome text  + original keyboard

/help and /privacy commands also edit the stored start message in-place.
"""
import re
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.ext import ContextTypes
from bot.utils.decorators import private_chat_only
from bot.database.db import get_setting

# Key used to remember the start message so /help and /privacy can edit it
_START_MSG_KEY = "start_msg"


# ── Persistent bottom keyboard ────────────────────────────────────────────────

def main_keyboard() -> ReplyKeyboardMarkup:
    """Persistent reply keyboard shown at the bottom of every private chat."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Create post")],
            [KeyboardButton("My posts"), KeyboardButton("Profile")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ── Text builders ─────────────────────────────────────────────────────────────

def _build_welcome_text(news_url: str | None) -> str:
    if news_url:
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


HELP_TEXT = (
    "*Post Forward Bot — Help*\n\n"
    "*How to use:*\n"
    "1\\. Add destination channels with /addchat\n"
    "2\\. Make sure I'm an admin in those channels\n"
    "3\\. Send any post to me — I'll ask you to confirm before forwarding\n\n"
    "*Commands:*\n"
    "/addchat `<chat_id>` — add a destination channel\n"
    "/removechat `<chat_id>` — remove a destination channel\n"
    "/listchats — view all destinations\n"
    "/myid — get your Telegram user ID\n"
    "/help — show this message\n\n"
    "*Tip:* Get a channel's ID by forwarding a message from it to @userinfobot"
)

PRIVACY_TEXT = (
    "*Privacy Policy*\n\n"
    "This bot stores only the following data:\n"
    "• Destination channel IDs and titles you configure\n"
    "• A log of forwarded messages \\(source chat, message ID, destination, timestamp\\)\n\n"
    "No personal messages, usernames, or contact data are stored\\.\n\n"
    "To request data deletion, contact the bot administrator\\."
)


# ── Keyboard builders ─────────────────────────────────────────────────────────

def _start_keyboard(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    deep_link = f"https://t.me/{bot_username}?start={user_id}"
    share_url  = f"https://t.me/share/url?url={deep_link}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("sʜᴀʀᴇ", url=share_url)],
        [
            InlineKeyboardButton("ʜᴇʟᴘ",    callback_data="start:help"),
            InlineKeyboardButton("ᴘʀɪᴠᴀᴄʏ", callback_data="start:privacy"),
        ],
    ])


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="start:back")],
    ])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_bot_username(context) -> str:
    return (await context.bot.get_me()).username


# ── Command handlers ──────────────────────────────────────────────────────────

@private_chat_only
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    news_url     = await get_setting("news_channel", scope="bot")
    welcome_text = _build_welcome_text(news_url)
    bot_username = await _get_bot_username(context)
    user_id      = update.effective_user.id

    # Send persistent bottom keyboard first (silent attachment to the chat)
    await update.message.reply_text(
        "👇 Use the keyboard below to get started",
        reply_markup=main_keyboard(),
    )

    # Send the welcome message with inline buttons
    msg = await update.message.reply_text(
        welcome_text,
        parse_mode="MarkdownV2",
        reply_markup=_start_keyboard(bot_username, user_id),
        disable_web_page_preview=True,
    )
    # Remember this message so /help and /privacy can edit it in-place
    context.user_data[_START_MSG_KEY] = {
        "msg_id":  msg.message_id,
        "chat_id": msg.chat.id,
    }


@private_chat_only
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get(_START_MSG_KEY)
    if state:
        try:
            await context.bot.edit_message_text(
                chat_id=state["chat_id"],
                message_id=state["msg_id"],
                text=HELP_TEXT,
                parse_mode="MarkdownV2",
                reply_markup=_back_keyboard(),
            )
            return
        except Exception:
            pass
    # Fallback if start message is gone
    msg = await update.message.reply_text(
        HELP_TEXT, parse_mode="MarkdownV2", reply_markup=_back_keyboard()
    )
    context.user_data[_START_MSG_KEY] = {
        "msg_id":  msg.message_id,
        "chat_id": msg.chat.id,
    }


@private_chat_only
async def privacy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get(_START_MSG_KEY)
    if state:
        try:
            await context.bot.edit_message_text(
                chat_id=state["chat_id"],
                message_id=state["msg_id"],
                text=PRIVACY_TEXT,
                parse_mode="MarkdownV2",
                reply_markup=_back_keyboard(),
            )
            return
        except Exception:
            pass
    # Fallback if start message is gone
    msg = await update.message.reply_text(
        PRIVACY_TEXT, parse_mode="MarkdownV2", reply_markup=_back_keyboard()
    )
    context.user_data[_START_MSG_KEY] = {
        "msg_id":  msg.message_id,
        "chat_id": msg.chat.id,
    }


# ── Profile handler ───────────────────────────────────────────────────────────

@private_chat_only
async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    name = (user.full_name or "").replace(".", "\\.").replace("-", "\\-").replace("(", "\\(").replace(")", "\\)")
    username_line = f"@{user.username}" if user.username else "—"
    text = (
        f"👤 *Profile*\n\n"
        f"*Name:* {name}\n"
        f"*ID:* `{user.id}`\n"
        f"*Username:* {username_line}\n\n"
        f"Use /usersettings to manage your preferences\\."
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


# ── Callback handler ──────────────────────────────────────────────────────────

async def start_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data    = query.data
    user_id = update.effective_user.id

    if data == "start:help":
        await query.edit_message_text(
            HELP_TEXT,
            parse_mode="MarkdownV2",
            reply_markup=_back_keyboard(),
        )

    elif data == "start:privacy":
        await query.edit_message_text(
            PRIVACY_TEXT,
            parse_mode="MarkdownV2",
            reply_markup=_back_keyboard(),
        )

    elif data == "start:back":
        news_url     = await get_setting("news_channel", scope="bot")
        welcome_text = _build_welcome_text(news_url)
        bot_username = await _get_bot_username(context)
        await query.edit_message_text(
            welcome_text,
            parse_mode="MarkdownV2",
            reply_markup=_start_keyboard(bot_username, user_id),
            disable_web_page_preview=True,
        )
