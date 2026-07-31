"""/usersettings command — inline panel to configure per-user settings.

Settings:
  log_channel  — Telegram channel ID/username where bot logs activity
  force_sub    — @channel users must be subscribed to before using the bot
  cookies      — arbitrary cookies string (e.g. for external services)

Flow:
  /usersettings  →  show panel (inline KB)
  tap button     →  ask for new value in same chat  (ConversationHandler)
  user replies   →  save, edit panel message back to updated values
  Close button   →  delete the panel message
"""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.error import BadRequest

from bot.db import get_user_settings, set_user_setting, upsert_user
from bot.keyboards import MAIN_MENU, CANCEL_MENU

# ── Conversation states ────────────────────────────────────────────────────────
AWAIT_LOG_CHANNEL = 20
AWAIT_FORCE_SUB   = 21
AWAIT_COOKIES     = 22


# ── Panel helpers ──────────────────────────────────────────────────────────────

def _fmt(value: str | None) -> str:
    return value if value else "not set"


def _panel_text(s: dict) -> str:
    return (
        "<b>Bot Settings</b>\n\n"
        f"Log Channel : <code>{_fmt(s.get('log_channel'))}</code>\n"
        f"Force Sub   : <code>{_fmt(s.get('force_sub'))}</code>\n\n"
        "Tap a button below to configure a setting."
    )


PANEL_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("ʟᴏɢ ᴄʜᴀɴɴᴇʟ", callback_data="us:log_channel")],
    [InlineKeyboardButton("ꜰᴏʀᴄᴇ sᴜʙ",   callback_data="us:force_sub")],
    [InlineKeyboardButton("ᴄʟᴏsᴇ",        callback_data="us:close")],
])


async def _refresh_panel(user_id: int, message) -> None:
    """Edit the existing panel message with fresh settings values."""
    s = await get_user_settings(user_id)
    try:
        await message.edit_text(_panel_text(s), parse_mode="HTML", reply_markup=PANEL_KB)
    except BadRequest:
        pass  # message unchanged — that's fine


# ── /botsettings entry ────────────────────────────────────────────────────────

async def usersettings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await upsert_user(user.id, user.username, user.first_name)
    s = await get_user_settings(user.id)
    await update.message.reply_html(_panel_text(s), reply_markup=PANEL_KB)


# ── Inline button dispatchers ──────────────────────────────────────────────────

async def _ask(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str,
               prompt: str) -> int:
    query = update.callback_query
    await query.answer()
    # Store which message to edit back and which key we're setting
    context.user_data["settings_key"]        = key
    context.user_data["settings_message_id"] = query.message.message_id
    context.user_data["settings_chat_id"]    = query.message.chat_id
    await query.message.reply_html(prompt, reply_markup=CANCEL_MENU)
    state_map = {"log_channel": AWAIT_LOG_CHANNEL, "force_sub": AWAIT_FORCE_SUB,
                 "cookies": AWAIT_COOKIES}
    return state_map[key]


async def btn_log_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _ask(
        update, context, "log_channel",
        "📢 <b>Log Channel</b>\n\n"
        "Send the channel ID or @username where activity should be logged.\n"
        "Example: <code>-1001234567890</code> or <code>@mychannel</code>\n\n"
        "Send <code>clear</code> to remove.",
    )


async def btn_force_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _ask(
        update, context, "force_sub",
        "🔒 <b>Force Subscribe</b>\n\n"
        "Send the @username of the channel users must subscribe to before using the bot.\n"
        "Example: <code>@mychannel</code>\n\n"
        "Send <code>clear</code> to remove.",
    )


async def btn_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _ask(
        update, context, "cookies",
        "🍪 <b>Cookies</b>\n\n"
        "Send your cookies string.\n\n"
        "Send <code>clear</code> to remove.",
    )


async def btn_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        await query.message.delete()
    except BadRequest:
        pass


# ── Receive new value ──────────────────────────────────────────────────────────

async def _receive_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    key  = context.user_data.get("settings_key")

    if not key:
        await update.message.reply_text("Something went wrong. Try /usersettings again.",
                                        reply_markup=MAIN_MENU)
        return ConversationHandler.END

    value = None if text.lower() == "clear" else text
    await set_user_setting(update.effective_user.id, key, value)

    verb = "cleared" if value is None else "saved"
    await update.message.reply_html(f"✅ <b>{key.replace('_',' ').title()}</b> {verb}.",
                                    reply_markup=MAIN_MENU)

    # Refresh the original panel message
    msg_id  = context.user_data.pop("settings_message_id", None)
    chat_id = context.user_data.pop("settings_chat_id", None)
    context.user_data.pop("settings_key", None)

    if msg_id and chat_id:
        s = await get_user_settings(update.effective_user.id)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=_panel_text(s),
                parse_mode="HTML",
                reply_markup=PANEL_KB,
            )
        except BadRequest:
            pass

    return ConversationHandler.END


async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("settings_key", None)
    context.user_data.pop("settings_message_id", None)
    context.user_data.pop("settings_chat_id", None)
    await update.message.reply_text("❌ Cancelled.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


# ── Build handler ──────────────────────────────────────────────────────────────

def build_settings_handler() -> ConversationHandler:
    any_text = filters.TEXT & ~filters.COMMAND & ~filters.Regex(r"^❌ Cancel$")
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(btn_log_channel, pattern=r"^us:log_channel$"),
            CallbackQueryHandler(btn_force_sub,   pattern=r"^us:force_sub$"),
            CallbackQueryHandler(btn_cookies,     pattern=r"^us:cookies$"),
        ],
        states={
            AWAIT_LOG_CHANNEL: [MessageHandler(any_text, _receive_value)],
            AWAIT_FORCE_SUB:   [MessageHandler(any_text, _receive_value)],
            AWAIT_COOKIES:     [MessageHandler(any_text, _receive_value)],
        },
        fallbacks=[
            MessageHandler(filters.Regex(r"^❌ Cancel$"), _cancel),
        ],
        name="user_settings",
        persistent=False,
    )
