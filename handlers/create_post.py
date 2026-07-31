"""Create-post conversation handler — @PostBot-style post settings flow.

States:
  WAITING_CONTENT   → user sends initial media / text
  POST_SETTINGS     → post-settings menu (Add text / Add buttons / Done / Cancel)
  WAITING_TEXT      → user sends caption / text to attach to the post
  WAITING_BUTTONS   → user sends button definitions
  WAITING_TITLE     → user gives the post a save-name before we persist it
"""
import json
import re
from typing import Any

from telegram import Update, Message, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from bot.db import create_post, get_user_settings
from bot.keyboards import MAIN_MENU, CANCEL_MENU, BACK_TO_POST_MENU, post_settings_keyboard

# ── State constants ────────────────────────────────────────────────────────────
WAITING_CONTENT = 1
POST_SETTINGS   = 2
WAITING_TEXT    = 3
WAITING_BUTTONS = 4
WAITING_TITLE   = 5

# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_media(message: Message) -> tuple[str | None, str | None]:
    """Return (media_type, file_id) from a Telegram message, or (None, None)."""
    if message.photo:
        return "photo", message.photo[-1].file_id
    if message.video:
        return "video", message.video.file_id
    if message.document:
        return "document", message.document.file_id
    return None, None


def _build_inline_kb(buttons_rows: list[list[dict]]) -> InlineKeyboardMarkup | None:
    """Build an InlineKeyboardMarkup from stored button rows, or None if empty."""
    if not buttons_rows:
        return None
    rows = []
    for row in buttons_rows:
        tg_row = []
        for btn in row:
            url = btn["url"]
            if url.startswith("@"):
                url = f"https://t.me/{url[1:]}"
            elif not url.startswith("http"):
                url = f"https://{url}"
            tg_row.append(InlineKeyboardButton(btn["text"], url=url))
        if tg_row:
            rows.append(tg_row)
    return InlineKeyboardMarkup(rows) if rows else None


async def _send_preview(chat_id: int, draft: dict, bot) -> None:
    """Send a live preview of the draft post to the user."""
    media_type = draft.get("media_type")
    file_id    = draft.get("file_id")
    content    = draft.get("content") or ""
    caption    = draft.get("caption") or ""
    text_pos   = draft.get("text_pos", "below")
    btn_rows   = draft.get("buttons_rows", [])
    reply_markup = _build_inline_kb(btn_rows)

    try:
        if media_type == "photo":
            cap = caption if text_pos == "below" else content
            if text_pos == "above" and content:
                await bot.send_message(chat_id, content, parse_mode="HTML")
            await bot.send_photo(
                chat_id, file_id,
                caption=cap or None,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            if text_pos == "below" and content and content != caption:
                await bot.send_message(chat_id, content, parse_mode="HTML")
        elif media_type == "video":
            await bot.send_video(
                chat_id, file_id,
                caption=caption or None,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            if content:
                await bot.send_message(chat_id, content, parse_mode="HTML")
        elif media_type == "document":
            await bot.send_document(
                chat_id, file_id,
                caption=caption or None,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            if content:
                await bot.send_message(chat_id, content, parse_mode="HTML")
        else:
            # text-only post
            await bot.send_message(
                chat_id,
                content or "(empty)",
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
    except Exception:
        pass  # preview best-effort


async def _show_post_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display the Post Settings screen with a live preview."""
    draft    = context.user_data.get("draft", {})
    text_pos = draft.get("text_pos", "below")
    chat_id  = update.effective_chat.id

    await update.effective_message.reply_text(
        "⚙️ <b>Post settings</b>\n\n"
        "Use the menu below to add text or buttons.\n\n"
        "<b>Here's a preview of your post:</b>",
        parse_mode="HTML",
        reply_markup=post_settings_keyboard(text_pos),
    )
    await _send_preview(chat_id, draft, context.bot)
    return POST_SETTINGS


# ── Entry ──────────────────────────────────────────────────────────────────────

async def ask_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["draft"] = {
        "media_type":   None,
        "file_id":      None,
        "content":      None,
        "caption":      None,
        "text_pos":     "below",
        "buttons_rows": [],
    }
    await update.effective_message.reply_text(
        "📝 <b>Create a new post</b>\n\n"
        "Send me the post content:\n"
        "• Text (HTML formatting supported)\n"
        "• Photo / video / document\n\n"
        "Type /cancel to abort.",
        parse_mode="HTML",
        reply_markup=CANCEL_MENU,
    )
    return WAITING_CONTENT


# ── Receive initial content ────────────────────────────────────────────────────

async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message    = update.message
    media_type, file_id = _extract_media(message)
    draft      = context.user_data.setdefault("draft", {})

    if media_type:
        draft.update(
            media_type=media_type,
            file_id=file_id,
            caption=message.caption or "",
            content=None,
        )
    else:
        draft.update(
            media_type=None,
            file_id=None,
            caption=None,
            content=message.text or "",
        )

    draft.setdefault("text_pos", "below")
    draft.setdefault("buttons_rows", [])
    return await _show_post_settings(update, context)


# ── Post settings menu ─────────────────────────────────────────────────────────

async def settings_add_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📄 <b>Add text</b>\n\n"
        "Send the text for your post.\n"
        "HTML formatting is supported: <b>bold</b>, <i>italic</i>, <code>code</code>, "
        '<a href="https://example.com">links</a>',
        parse_mode="HTML",
        reply_markup=BACK_TO_POST_MENU,
    )
    return WAITING_TEXT


async def settings_add_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    template = (
        "Ads — https://t.me/example — green\n"
        "Channel — https://t.me/channel\n"
        "Support — https://t.me/support | Docs — https://example.com/docs"
    )
    await update.message.reply_html(
        "Adding buttons\n\n"
        "• New line = new button row\n"
        "• Separator between text and URL: <code> — </code> or <code> | </code>\n"
        "• Multiple buttons in one row: <code>Btn1 — url1 | Btn2 — url2</code>\n"
        "• Color hint at end: <code>green</code>, <code>blue</code>, or <code>red</code> (optional)\n\n"
        "<b>Template:</b>\n"
        f"<pre>{template}</pre>\n\n"
        "Send your buttons:",
        reply_markup=BACK_TO_POST_MENU,
    )
    return WAITING_BUTTONS


async def settings_toggle_text_pos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft    = context.user_data.get("draft", {})
    current  = draft.get("text_pos", "below")
    draft["text_pos"] = "above" if current == "below" else "below"
    return await _show_post_settings(update, context)


async def settings_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📌 <b>Give your post a title</b>\n\n"
        "This is just for you — a short name so you can find it in <i>My posts</i>.",
        parse_mode="HTML",
        reply_markup=CANCEL_MENU,
    )
    return WAITING_TITLE


async def settings_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("draft", None)
    await update.message.reply_text("❌ Post creation cancelled.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


# ── Receive text for post ──────────────────────────────────────────────────────

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text  = update.message.text or ""
    draft = context.user_data.get("draft", {})

    if draft.get("media_type"):
        draft["caption"] = text
    else:
        draft["content"] = text

    return await _show_post_settings(update, context)


async def back_to_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _show_post_settings(update, context)


# ── Receive buttons ────────────────────────────────────────────────────────────

_DASH_RE = re.compile(r"\s*[—–\-]\s*")   # em-dash, en-dash, or hyphen
_COLOR_RE = re.compile(r"\s*(green|blue|red)\s*$", re.IGNORECASE)


def _parse_buttons(raw: str) -> tuple[list[list[dict]], str | None]:
    """
    Parse raw button text.  Returns (rows, error_message_or_None).

    Line syntax:   text — URL [— color]   (em/en-dash or hyphen)
                   text | URL             (pipe also accepted as text-URL separator)
    Row separator: multiple buttons on one line separated by  |  between complete
                   definitions, e.g.  Btn1 — url1 | Btn2 — url2
    """
    rows: list[list[dict]] = []

    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        # Split by | to get candidate button fragments for this row.
        # Re-group fragments: if a fragment has no dash-separator and doesn't
        # start with http, but the NEXT fragment does start with http, the user
        # used "text | URL" style → merge them into one button definition.
        raw_parts = [p.strip() for p in line.split("|")]
        grouped: list[str] = []
        i = 0
        while i < len(raw_parts):
            part = raw_parts[i]
            if (
                part
                and not _DASH_RE.search(part)
                and not part.lower().startswith("http")
                and i + 1 < len(raw_parts)
                and raw_parts[i + 1].strip().lower().startswith("http")
            ):
                # "text | URL" pair — join with em-dash so the dash-splitter works
                grouped.append(f"{part} — {raw_parts[i + 1].strip()}")
                i += 2
            else:
                if part:
                    grouped.append(part)
                i += 1

        row_buttons: list[dict] = []

        for part in grouped:
            part = part.strip()
            if not part:
                continue

            # Strip optional trailing color hint
            color = "blue"
            m = _COLOR_RE.search(part)
            if m:
                color = m.group(1).lower()
                part = part[: m.start()].strip()

            # Split on first dash-like character (maxsplit=1 keeps URL intact)
            segments = _DASH_RE.split(part, maxsplit=1)
            if len(segments) < 2:
                return [], (
                    "⚠️ <b>Format error.</b> Check that there is a dash between "
                    "the text and the link, and try again.\n\n"
                    "Example: <code>Button text — https://example.com</code>\n"
                    "or: <code>Button text | https://example.com</code>"
                )

            btn_text = segments[0].strip()
            btn_url  = segments[1].strip()

            if not btn_text:
                return [], "⚠️ <b>Format error.</b> Button text cannot be empty."
            if not btn_url:
                return [], "⚠️ <b>Format error.</b> Button URL cannot be empty."

            row_buttons.append({"text": btn_text, "url": btn_url, "color": color})

        if row_buttons:
            rows.append(row_buttons)

    if not rows:
        return [], "⚠️ <b>Format error.</b> No valid buttons found."

    return rows, None


async def receive_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw   = update.message.text or ""
    rows, error = _parse_buttons(raw)

    if error:
        await update.message.reply_html(
            error,
            reply_markup=BACK_TO_POST_MENU,
        )
        return WAITING_BUTTONS  # stay, let user fix it

    draft = context.user_data.get("draft", {})
    draft["buttons_rows"] = rows
    return await _show_post_settings(update, context)


# ── Receive title & save ───────────────────────────────────────────────────────

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title = (update.message.text or "").strip()
    if not title:
        await update.message.reply_text("Title can't be empty. Please send a title.")
        return WAITING_TITLE
    if len(title) > 100:
        await update.message.reply_text("Title is too long (max 100 chars). Try a shorter one.")
        return WAITING_TITLE

    draft   = context.user_data.get("draft", {})
    user_id = update.effective_user.id

    btn_rows    = draft.get("buttons_rows", [])
    buttons_json = json.dumps(btn_rows, ensure_ascii=False) if btn_rows else None

    post_id = await create_post(
        user_id      = user_id,
        title        = title,
        content      = draft.get("content"),
        media_type   = draft.get("media_type"),
        file_id      = draft.get("file_id"),
        caption      = draft.get("caption"),
        text_pos     = draft.get("text_pos", "below"),
        buttons_json = buttons_json,
    )
    context.user_data.pop("draft", None)

    btn_info = f" + {sum(len(r) for r in btn_rows)} button(s)" if btn_rows else ""
    await update.message.reply_html(
        f"🎉 <b>Post saved!</b>\n\n"
        f"📌 <b>{title}</b>{btn_info}\n"
        f"🆔 Post #{post_id}\n\n"
        "Find it any time in <b>My posts</b> 📋",
        reply_markup=MAIN_MENU,
    )

    # ── Forward to log channel if configured ──────────────────────────────────
    settings = await get_user_settings(user_id)
    log_channel = settings.get("log_channel")
    if log_channel:
        user = update.effective_user
        username_line = f"@{user.username}" if user.username else f"#{user.id}"
        header = (
            f"📥 <b>New post saved</b>\n"
            f"👤 User: {username_line} (<code>{user.id}</code>)\n"
            f"📌 Title: <b>{title}</b>  •  Post #{post_id}\n"
            f"{'─' * 24}"
        )
        reply_markup = _build_inline_kb(btn_rows) if btn_rows else None
        try:
            await context.bot.send_message(log_channel, header, parse_mode="HTML")
            media_type = draft.get("media_type")
            file_id    = draft.get("file_id")
            caption    = draft.get("caption") or ""
            content    = draft.get("content") or ""
            if media_type == "photo":
                await context.bot.send_photo(
                    log_channel, file_id,
                    caption=caption or None, parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            elif media_type == "video":
                await context.bot.send_video(
                    log_channel, file_id,
                    caption=caption or None, parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            elif media_type == "document":
                await context.bot.send_document(
                    log_channel, file_id,
                    caption=caption or None, parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            else:
                await context.bot.send_message(
                    log_channel, content or "(empty post)",
                    parse_mode="HTML", reply_markup=reply_markup,
                )
        except Exception as e:
            # Never crash the save flow because of a log error
            import logging
            logging.getLogger(__name__).warning("Log channel send failed: %s", e)

    return ConversationHandler.END


# ── Cancel ─────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("draft", None)
    await update.message.reply_text("❌ Post creation cancelled.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


# ── Build handler ──────────────────────────────────────────────────────────────

def build_create_post_handler() -> ConversationHandler:
    _text_only = filters.TEXT & ~filters.COMMAND

    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^📝 Create post$"), ask_content),
            CallbackQueryHandler(ask_content, pattern=r"^create:new$"),
        ],
        states={
            WAITING_CONTENT: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL)
                    & ~filters.COMMAND
                    & ~filters.Regex(r"^❌ Cancel$"),
                    receive_content,
                ),
            ],
            POST_SETTINGS: [
                MessageHandler(filters.Regex(r"^Add text$"),           settings_add_text),
                MessageHandler(filters.Regex(r"^Add buttons$"),        settings_add_buttons),
                MessageHandler(filters.Regex(r"^[⬇⬆️]+ Text:"),       settings_toggle_text_pos),
                MessageHandler(filters.Regex(r"^✅ Done$"),             settings_done),
                MessageHandler(filters.Regex(r"^❌ Cancel$"),           settings_cancel),
            ],
            WAITING_TEXT: [
                MessageHandler(filters.Regex(r"^🔙 Back to post$"),     back_to_settings),
                MessageHandler(
                    _text_only & ~filters.Regex(r"^🔙 Back to post$"),
                    receive_text,
                ),
            ],
            WAITING_BUTTONS: [
                MessageHandler(filters.Regex(r"^🔙 Back to post$"),     back_to_settings),
                MessageHandler(
                    _text_only & ~filters.Regex(r"^🔙 Back to post$"),
                    receive_buttons,
                ),
            ],
            WAITING_TITLE: [
                MessageHandler(
                    _text_only & ~filters.Regex(r"^❌ Cancel$"),
                    receive_title,
                ),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex(r"^❌ Cancel$"), cancel),
            CommandHandler("cancel", cancel),
        ],
        name="create_post",
        persistent=False,
    )
