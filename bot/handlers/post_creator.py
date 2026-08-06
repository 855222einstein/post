"""
/newpost — freeform post creator with photo, sticker (incl. premium), or text-only.

Flow
----
1. /newpost        → ask for poster image OR sticker (or /skip for text-only)
2. Photo/Sticker/skip → "Send your post text" (or /skip for media-only)
3. Text/skip       → "Add buttons" one per line as  Label | @username_or_url
                     (or /skip for no buttons)
4. Buttons/skip    → preview + Post / Edit / Cancel
5. Post            → send to all destination channels
6. Edit            → restart from step 2
7. Cancel          → abort

Button format examples
----------------------
  GET FILES | @YourBot
  GET FILES | https://t.me/YourBot?start=abc
  Watch Now | https://example.com
  PART 1 | @Bot1
  PART 2 | @Bot2

Each line becomes one button row.  @username auto-converts to https://t.me/username.
Send /cancel at any step to abort.
"""
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.ext.filters import ChatType

import re
import secrets

from bot.database.db import list_destinations, save_post, list_user_posts, delete_user_post
from bot.utils.decorators import admin_only, admin_or_sudo
import logging

logger = logging.getLogger(__name__)

# ── States ────────────────────────────────────────────────────────────────────
MEDIA, POST_TEXT, BUTTONS, CONFIRM = range(4)

_DATA = "movie_post"


# ── Button helpers ────────────────────────────────────────────────────────────

def _normalize_url(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("@"):
        return f"https://t.me/{raw[1:]}"
    if raw.startswith("t.me/"):
        return f"https://{raw}"
    return raw


def _parse_buttons(text: str) -> InlineKeyboardMarkup | None:
    rows = []
    for line in text.strip().splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        label, _, raw_url = line.partition("|")
        label = label.strip()
        url   = _normalize_url(raw_url)
        if label and url:
            rows.append([InlineKeyboardButton(label, url=url)])
    return InlineKeyboardMarkup(rows) if rows else None


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("ᴘᴏsᴛ",   callback_data="np:confirm"),
        InlineKeyboardButton("ᴇᴅɪᴛ",   callback_data="np:edit"),
        InlineKeyboardButton("ᴄᴀɴᴄᴇʟ", callback_data="np:cancel"),
    ]])


# ── Entry ─────────────────────────────────────────────────────────────────────

@admin_or_sudo
async def newpost_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[_DATA] = {}
    await update.message.reply_text(
        "*New Post*\n\n"
        "Send a *poster image* or a *sticker* (including premium stickers), "
        "or /skip for text-only.",
        parse_mode="Markdown",
    )
    return MEDIA


# ── Step 1 : Media (photo / sticker / skip) ───────────────────────────────────

async def step_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[_DATA]["photo_file_id"]   = update.message.photo[-1].file_id
    context.user_data[_DATA]["sticker_file_id"] = None
    await _ask_text(update)
    return POST_TEXT


async def step_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    sticker = update.message.sticker
    is_premium = getattr(sticker, "is_premium", False)
    context.user_data[_DATA]["sticker_file_id"] = sticker.file_id
    context.user_data[_DATA]["is_premium"]       = is_premium
    context.user_data[_DATA]["photo_file_id"]    = None
    label = "Premium sticker" if is_premium else "Sticker"
    await update.message.reply_text(
        f"{label} received.\n\nNow send your *post text*, or /skip for sticker-only.",
        parse_mode="Markdown",
    )
    return POST_TEXT


async def step_skip_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[_DATA]["photo_file_id"]   = None
    context.user_data[_DATA]["sticker_file_id"] = None
    await _ask_text(update)
    return POST_TEXT


async def _ask_text(update: Update) -> None:
    await update.message.reply_text(
        "Send your post text (write it exactly as you want it to appear), "
        "or /skip for media-only:",
    )


# ── Step 2 : Post text (or skip) ─────────────────────────────────────────────

async def step_post_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[_DATA]["text"] = update.message.text or ""
    await _ask_buttons(update)
    return BUTTONS


async def step_skip_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[_DATA]["text"] = ""
    await _ask_buttons(update)
    return BUTTONS


async def _ask_buttons(update: Update) -> None:
    await update.message.reply_text(
        "*Add buttons* — one per line:\n\n"
        "`Label | @username_or_url`\n\n"
        "Examples:\n"
        "`GET FILES | @YourBot`\n"
        "`PART 1 | @Bot1`\n"
        "`Watch | https://t.me/YourBot?start=abc`\n\n"
        "Or /skip for no buttons.",
        parse_mode="Markdown",
    )


# ── Step 3 : Buttons (or skip) ────────────────────────────────────────────────

async def step_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text or ""
    kb = _parse_buttons(raw)
    if kb is None:
        await update.message.reply_text(
            "No valid buttons found.\n\n"
            "Each line must be `Label | @username_or_url`.\n"
            "Try again or /skip.",
            parse_mode="Markdown",
        )
        return BUTTONS
    context.user_data[_DATA]["buttons_raw"] = raw
    context.user_data[_DATA]["buttons_kb"]  = kb
    return await _show_preview(update, context)


async def step_skip_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[_DATA]["buttons_raw"] = ""
    context.user_data[_DATA]["buttons_kb"]  = None
    return await _show_preview(update, context)


# ── Preview ───────────────────────────────────────────────────────────────────

async def _show_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data       = context.user_data[_DATA]
    text       = data.get("text", "")
    user_kb    = data.get("buttons_kb")
    ctrl_kb    = _confirm_keyboard()

    await update.message.reply_text("Preview:")

    if data.get("sticker_file_id"):
        # Stickers can't carry a caption — send sticker, then text separately
        await update.message.reply_sticker(sticker=data["sticker_file_id"])
        if text:
            await update.message.reply_text(text, reply_markup=user_kb)
        elif user_kb:
            await update.message.reply_text(".", reply_markup=user_kb)
    elif data.get("photo_file_id"):
        await update.message.reply_photo(
            photo=data["photo_file_id"],
            caption=text or None,
            reply_markup=user_kb,
        )
    else:
        await update.message.reply_text(text or ".", reply_markup=user_kb)

    await update.message.reply_text(
        "Check your post above, then choose:",
        reply_markup=ctrl_kb,
    )
    return CONFIRM


# ── Confirm / Edit / Cancel ───────────────────────────────────────────────────

async def confirm_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Sending...")

    data    = context.user_data.get(_DATA, {})
    text    = data.get("text", "")
    user_kb = data.get("buttons_kb")

    destinations = await list_destinations()
    if not destinations:
        await query.message.reply_text(
            "No destination channels configured. Add one with /addchat first."
        )
        return ConversationHandler.END

    success, errors = 0, []
    for dest in destinations:
        try:
            chat_id = dest["chat_id"]

            if data.get("sticker_file_id"):
                # Send sticker first (no caption possible on stickers)
                await context.bot.send_sticker(
                    chat_id=chat_id,
                    sticker=data["sticker_file_id"],
                )
                # Follow up with text + buttons if provided
                if text or user_kb:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=text if text else ".",
                        reply_markup=user_kb,
                    )

            elif data.get("photo_file_id"):
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=data["photo_file_id"],
                    caption=text or None,
                    reply_markup=user_kb,
                )

            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text if text else ".",
                    reply_markup=user_kb,
                )

            success += 1
        except Exception as exc:
            errors.append(f"- {dest['title']}: {exc}")
            logger.warning("Failed to post to %s: %s", dest["chat_id"], exc)

    result = f"Posted to {success}/{len(destinations)} channel(s)."
    if errors:
        result += "\n\nFailed:\n" + "\n".join(errors)

    # Save post to DB so it appears in /myposts
    if success:
        user_id  = update.effective_user.id
        short_id = secrets.token_hex(7)          # 14-char lowercase hex
        await save_post(
            user_id         = user_id,
            short_id        = short_id,
            text            = data.get("text") or None,
            photo_file_id   = data.get("photo_file_id"),
            sticker_file_id = data.get("sticker_file_id"),
            buttons_raw     = data.get("buttons_raw") or None,
        )

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await query.message.reply_text(result)

    context.user_data.pop(_DATA, None)
    return ConversationHandler.END


async def edit_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await query.message.reply_text(
        "*New Post*\n\n"
        "Send a *poster image* or a *sticker* (including premium stickers), "
        "or /skip for text-only.",
        parse_mode="Markdown",
    )
    return MEDIA


async def cancel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop(_DATA, None)
    if update.callback_query:
        await update.callback_query.answer("Cancelled.")
        try:
            await update.callback_query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await update.callback_query.message.reply_text("Post cancelled.")
    else:
        await update.message.reply_text("Post creation cancelled.")
    return ConversationHandler.END


# ── /myposts ──────────────────────────────────────────────────────────────────

@admin_or_sudo
async def myposts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    posts   = await list_user_posts(user_id)

    if not posts:
        await update.message.reply_text("📭 You have no saved posts yet.\n\nUse /newpost to create one.")
        return

    bot_username = (await context.bot.get_me()).username
    lines = ["📦 *My posts*\n"]
    for i, p in enumerate(posts, 1):
        preview = (p["text"] or "").strip().replace("*", "").replace("_", "")
        preview = preview[:40] + ("…" if len(preview) > 40 else "")
        label   = preview or "📎 media"
        lines.append(
            f"{i}\\. {p['short_id']}\n"
            f"@{bot_username} {p['short_id']}\n"
            f"/delete\\_{p['id']}  — _{label}_"
        )

    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode="MarkdownV2",
    )


# ── /delete_<id> ──────────────────────────────────────────────────────────────

@admin_or_sudo
async def delete_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    m    = re.match(r"^/delete_(\d+)", text)
    if not m:
        return
    post_id = int(m.group(1))
    user_id = update.effective_user.id
    deleted = await delete_user_post(post_id, user_id)
    if deleted:
        await update.message.reply_text(f"✅ Post #{post_id} deleted.")
    else:
        await update.message.reply_text(f"❌ Post #{post_id} not found (or not yours).")


# ── ConversationHandler factory ───────────────────────────────────────────────

def build_newpost_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(ChatType.PRIVATE & filters.Regex(r"^Create post$"), newpost_start),
        ],
        states={
            MEDIA: [
                MessageHandler(filters.PHOTO, step_photo),
                MessageHandler(filters.Sticker.ALL, step_sticker),
                CommandHandler("skip", step_skip_media),
            ],
            POST_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step_post_text),
                CommandHandler("skip", step_skip_text),
            ],
            BUTTONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step_buttons),
                CommandHandler("skip", step_skip_buttons),
            ],
            CONFIRM: [
                CallbackQueryHandler(confirm_post, pattern=r"^np:confirm$"),
                CallbackQueryHandler(edit_post,    pattern=r"^np:edit$"),
                CallbackQueryHandler(cancel_post,  pattern=r"^np:cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_post)],
        per_user=True,
        per_chat=True,
        allow_reentry=True,
    )
