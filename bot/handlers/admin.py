"""
Admin command handlers: /addchat, /removechat, /listchats, /myid.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database.db import add_destination, remove_destination, list_destinations
from bot.utils.decorators import admin_only, private_chat_only
from bot.utils.helpers import forward_message_to_all, build_forward_summary

# ── /myid ─────────────────────────────────────────────────────────────────────

@private_chat_only
async def myid_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    username = f"@{user.username}" if user.username else "_(no username)_"
    await update.message.reply_text(
        f"Your Telegram ID: `{user.id}`\nUsername: {username}",
        parse_mode="Markdown",
    )


# ── /addchat ──────────────────────────────────────────────────────────────────

@admin_only
@private_chat_only
async def addchat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Usage: `/addchat <chat_id>`\nExample: `/addchat -1001234567890`",
            parse_mode="Markdown",
        )
        return

    chat_id = context.args[0].strip()

    try:
        chat_info = await context.bot.get_chat(chat_id)
        title = getattr(chat_info, "title", None) or chat_id
    except Exception as exc:
        await update.message.reply_text(
            f"Could not reach that chat.\n"
            f"Make sure the bot is an *admin* in the channel and the ID is correct.\n\n"
            f"Error: `{exc}`",
            parse_mode="Markdown",
        )
        return

    added = await add_destination(chat_id, title)
    if added:
        await update.message.reply_text(
            f"Added *{title}* (`{chat_id}`) to destinations.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"*{title}* is already in the destination list.",
            parse_mode="Markdown",
        )


# ── /removechat ───────────────────────────────────────────────────────────────

@admin_only
@private_chat_only
async def removechat_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not context.args:
        await update.message.reply_text(
            "Usage: `/removechat <chat_id>`\nExample: `/removechat -1001234567890`",
            parse_mode="Markdown",
        )
        return

    chat_id = context.args[0].strip()
    removed = await remove_destination(chat_id)
    if removed:
        await update.message.reply_text(
            f"Removed `{chat_id}` from destinations.", parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"`{chat_id}` was not found in the destination list.",
            parse_mode="Markdown",
        )


# ── /listchats ────────────────────────────────────────────────────────────────

@admin_only
@private_chat_only
async def listchats_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    destinations = await list_destinations()
    if not destinations:
        await update.message.reply_text(
            "No destination channels configured yet.\n"
            "Use `/addchat <chat_id>` to add one.",
            parse_mode="Markdown",
        )
        return

    lines = [
        f"{i + 1}. *{d['title']}*\n   ID: `{d['chat_id']}`\n   Added: {d['added_at'][:10]}"
        for i, d in enumerate(destinations)
    ]
    await update.message.reply_text(
        f"*Destination Channels ({len(destinations)}):*\n\n" + "\n\n".join(lines),
        parse_mode="Markdown",
    )


# ── broadcast confirmation (post handler) ────────────────────────────────────

@admin_only
@private_chat_only
async def broadcast_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Triggered when an admin sends any content to the bot in a private chat.
    Shows a confirmation keyboard before forwarding.
    """
    destinations = await list_destinations()
    if not destinations:
        await update.message.reply_text(
            "No destination channels configured yet.\n"
            "Use `/addchat <chat_id>` to add one first.",
            parse_mode="Markdown",
        )
        return

    dest_list = "\n".join(f"• {d['title']}" for d in destinations)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "ꜰᴏʀᴡᴀʀᴅ",
                    callback_data=f"fwd:{update.effective_chat.id}:{update.message.message_id}",
                ),
                InlineKeyboardButton("ᴄᴀɴᴄᴇʟ", callback_data="cancel"),
            ]
        ]
    )
    await update.message.reply_text(
        f"Forward this post to *{len(destinations)}* channel(s)?\n\n{dest_list}",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
