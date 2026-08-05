"""
/botsettings and /usersettings — interactive settings panels.

Design rule
-----------
Telegram re-renders bubble corners whenever a neighbouring message is added/removed
(changing whether the bubble is "last in group").  To keep the bubble shape fixed,
every interaction edits the SAME message — never sends a new one.

To avoid changing the text size (which would change the bubble height), field
selection only swaps the inline keyboard; the text stays the same.
Text is only updated when a value is actually saved or reset.

Flow
----
1. /botsettings  → message: overview text + field buttons
2. Tap field     → edit_message_reply_markup only → shows Set / Reset / Back
3. Tap Back      → edit_message_reply_markup only → restores field buttons
4. Tap Set       → edit_message_text → ask for value (same message)
5. User types    → value saved; edit_message_text → fresh overview + field buttons
6. Tap Reset     → value cleared; edit_message_text → fresh overview + field buttons
7. Tap Close     → message deleted
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.database.db import get_setting, set_setting, reset_setting
from bot.utils.decorators import admin_only, private_chat_only

# ── Setting definitions ───────────────────────────────────────────────────────

BOT_FIELDS: list[dict] = [
    {"key": "log_channel",  "label": "Log Channel",  "hint": "Send the channel ID (e.g. -1001234567890)"},
    {"key": "force_sub",    "label": "Force Sub",    "hint": "Send the channel username or ID users must join"},
    {"key": "cookies",      "label": "Cookies",      "hint": "Send the cookie string"},
]

USER_FIELDS: list[dict] = [
    {"key": "language",      "label": "Language",       "hint": "Send your preferred language (e.g. English)"},
    {"key": "notifications", "label": "Notifications",  "hint": "Send 'on' or 'off'"},
    {"key": "forward_mode",  "label": "Forward Mode",   "hint": "Send 'copy' (no tag) or 'forward' (shows source)"},
]

_AWAIT_KEY = "awaiting_setting"


# ── Text builders ─────────────────────────────────────────────────────────────

def _fmt(value: str | None) -> str:
    return value if value else "not set"


async def _bot_settings_text(user_id: int) -> str:
    lines = ["*Bot Settings*\n"]
    for f in BOT_FIELDS:
        val = await get_setting(f["key"], scope="bot")
        lines.append(f"{f['label']:<12}: {_fmt(val)}")
    lines.append("\nTap a button below to configure a setting.")
    return "\n".join(lines)


async def _user_settings_text(user_id: int) -> str:
    lines = ["*User Settings*\n"]
    for f in USER_FIELDS:
        val = await get_setting(f["key"], scope=f"user:{user_id}")
        lines.append(f"{f['label']:<14}: {_fmt(val)}")
    lines.append("\nTap a button below to configure a setting.")
    return "\n".join(lines)


# ── Keyboard builders ─────────────────────────────────────────────────────────

def _bot_settings_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f["label"], callback_data=f"bs:field:{f['key']}")] for f in BOT_FIELDS]
    rows.append([InlineKeyboardButton("Close", callback_data="bs:close")])
    return InlineKeyboardMarkup(rows)


def _user_settings_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f["label"], callback_data=f"us:field:{f['key']}")] for f in USER_FIELDS]
    rows.append([InlineKeyboardButton("Close", callback_data="us:close")])
    return InlineKeyboardMarkup(rows)


def _field_keyboard(scope_prefix: str, field_key: str, field_label: str) -> InlineKeyboardMarkup:
    """Keyboard shown after tapping a field — Set / Reset / Back, all in the same message."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Set {field_label}",   callback_data=f"{scope_prefix}:set:{field_key}")],
        [InlineKeyboardButton(f"Reset {field_label}", callback_data=f"{scope_prefix}:reset:{field_key}")],
        [InlineKeyboardButton("Back",                 callback_data=f"{scope_prefix}:back")],
    ])


# ── Commands ──────────────────────────────────────────────────────────────────

@admin_only
@private_chat_only
async def botsettings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = await _bot_settings_text(update.effective_user.id)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=_bot_settings_keyboard())


@private_chat_only
async def usersettings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = await _user_settings_text(update.effective_user.id)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=_user_settings_keyboard())


# ── Callback router ───────────────────────────────────────────────────────────

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data: str = query.data or ""
    user_id = update.effective_user.id

    # ── Bot settings ──────────────────────────────────────────────────────────

    if data.startswith("bs:field:"):
        key = data[len("bs:field:"):]
        field = next((f for f in BOT_FIELDS if f["key"] == key), None)
        if not field:
            return
        # Keyboard-only swap — text unchanged, bubble shape preserved
        await query.edit_message_reply_markup(
            reply_markup=_field_keyboard("bs", key, field["label"])
        )

    elif data == "bs:back":
        # Keyboard-only swap back to main menu
        await query.edit_message_reply_markup(reply_markup=_bot_settings_keyboard())

    elif data.startswith("bs:set:"):
        key = data[len("bs:set:"):]
        field = next((f for f in BOT_FIELDS if f["key"] == key), None)
        if not field:
            return
        context.user_data[_AWAIT_KEY] = {
            "scope":   "bot",
            "key":     key,
            "label":   field["label"],
            "menu":    "bs",
            "msg_id":  query.message.message_id,
            "chat_id": query.message.chat.id,
        }
        # Edit text to ask for value (same bubble)
        await query.edit_message_text(
            f"*{field['label']}*\n\n{field['hint']}\n\nSend your value now, or /cancel to abort.",
            parse_mode="Markdown",
        )

    elif data.startswith("bs:reset:"):
        key = data[len("bs:reset:"):]
        field = next((f for f in BOT_FIELDS if f["key"] == key), None)
        if field:
            await reset_setting(key, scope="bot")
        text = await _bot_settings_text(user_id)
        await query.edit_message_text(
            f"*{field['label'] if field else key}* has been reset.\n\n" + text,
            parse_mode="Markdown",
            reply_markup=_bot_settings_keyboard(),
        )

    elif data == "bs:close":
        try:
            await query.message.delete()
        except Exception:
            pass

    # ── User settings ─────────────────────────────────────────────────────────

    elif data.startswith("us:field:"):
        key = data[len("us:field:"):]
        field = next((f for f in USER_FIELDS if f["key"] == key), None)
        if not field:
            return
        # Keyboard-only swap — text unchanged, bubble shape preserved
        await query.edit_message_reply_markup(
            reply_markup=_field_keyboard("us", key, field["label"])
        )

    elif data == "us:back":
        # Keyboard-only swap back to main menu
        await query.edit_message_reply_markup(reply_markup=_user_settings_keyboard())

    elif data.startswith("us:set:"):
        key = data[len("us:set:"):]
        field = next((f for f in USER_FIELDS if f["key"] == key), None)
        if not field:
            return
        context.user_data[_AWAIT_KEY] = {
            "scope":   f"user:{user_id}",
            "key":     key,
            "label":   field["label"],
            "menu":    "us",
            "msg_id":  query.message.message_id,
            "chat_id": query.message.chat.id,
        }
        # Edit text to ask for value (same bubble)
        await query.edit_message_text(
            f"*{field['label']}*\n\n{field['hint']}\n\nSend your value now, or /cancel to abort.",
            parse_mode="Markdown",
        )

    elif data.startswith("us:reset:"):
        key = data[len("us:reset:"):]
        field = next((f for f in USER_FIELDS if f["key"] == key), None)
        if field:
            await reset_setting(key, scope=f"user:{user_id}")
        text = await _user_settings_text(user_id)
        await query.edit_message_text(
            f"*{field['label'] if field else key}* has been reset.\n\n" + text,
            parse_mode="Markdown",
            reply_markup=_user_settings_keyboard(),
        )

    elif data == "us:close":
        try:
            await query.message.delete()
        except Exception:
            pass


# ── Input capture ─────────────────────────────────────────────────────────────

async def settings_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Captures the typed value after Set is tapped.
    Saves it then edits the original message back to the settings overview.
    Runs at group=-1 so it fires before the broadcast handler.
    """
    state = context.user_data.get(_AWAIT_KEY)
    if not state:
        return

    value = (update.message.text or "").strip()
    if not value:
        await update.message.reply_text("Empty value — please send a non-empty value or /cancel.")
        return

    await set_setting(state["key"], value, scope=state["scope"])
    context.user_data.pop(_AWAIT_KEY, None)

    # Delete the user's typed message
    try:
        await update.message.delete()
    except Exception:
        pass

    # Edit the original settings message back to the overview (same bubble)
    user_id = update.effective_user.id
    if state["menu"] == "bs":
        menu_text = await _bot_settings_text(user_id)
        kb = _bot_settings_keyboard()
    else:
        menu_text = await _user_settings_text(user_id)
        kb = _user_settings_keyboard()

    try:
        await context.bot.edit_message_text(
            chat_id=state["chat_id"],
            message_id=state["msg_id"],
            text=f"*{state['label']}* saved.\n\n{menu_text}",
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception:
        await update.message.reply_text(
            f"*{state['label']}* saved.\n\n{menu_text}",
            parse_mode="Markdown",
            reply_markup=kb,
        )


async def cancel_settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancels an in-progress Set operation."""
    if _AWAIT_KEY in context.user_data:
        state = context.user_data.pop(_AWAIT_KEY)
        await update.message.reply_text(
            f"Cancelled — *{state['label']}* was not changed.",
            parse_mode="Markdown",
        )
