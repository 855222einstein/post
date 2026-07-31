"""My posts handler — list, send, edit, delete saved posts."""
import json

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram.error import BadRequest

from bot.db import get_posts, get_post, delete_post, update_post
from bot.keyboards import (
    MAIN_MENU,
    CANCEL_MENU,
    post_action_keyboard,
    confirm_delete_keyboard,
    posts_navigation_keyboard,
    edit_field_keyboard,
)

POSTS_PER_PAGE = 5

# Conversation states for editing
EDIT_WAITING_TITLE = 10
EDIT_WAITING_CONTENT = 11

# ── List posts ─────────────────────────────────────────────────────────────────

async def show_my_posts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    posts = await get_posts(user_id)
    context.user_data["posts_cache"] = posts
    await _render_posts_page(update, context, page=0, posts=posts, send_new=True)


async def _render_posts_page(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    page: int,
    posts: list[dict],
    send_new: bool = False,
) -> None:
    if not posts:
        text = (
            "📋 <b>My posts</b>\n\n"
            "You don't have any saved posts yet.\n"
            "Tap <b>📝 Create post</b> to make your first one!"
        )
        if send_new:
            await update.message.reply_html(text, reply_markup=MAIN_MENU)
        else:
            await update.callback_query.edit_message_text(text, parse_mode="HTML")
        return

    total_pages = max(1, (len(posts) + POSTS_PER_PAGE - 1) // POSTS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    slice_ = posts[page * POSTS_PER_PAGE : (page + 1) * POSTS_PER_PAGE]

    lines = [f"📋 <b>My posts</b>  ({len(posts)} total)\n"]
    for i, p in enumerate(slice_, start=page * POSTS_PER_PAGE + 1):
        preview = ""
        if p["content"]:
            preview = p["content"][:40].replace("\n", " ")
            if len(p["content"]) > 40:
                preview += "…"
        elif p["media_type"]:
            preview = f"[{p['media_type']}]"
        lines.append(f"{i}. 📌 <b>{p['title']}</b>\n   {preview}")

    text = "\n".join(lines)
    nav_kb = posts_navigation_keyboard(page, total_pages)

    if send_new:
        # Build a list of buttons: one per post on this page
        rows = []
        for p in slice_:
            rows.append([InlineKeyboardButton(f"📌 {p['title']}", callback_data=f"view:{p['id']}")])

        # Merge nav buttons if any
        if nav_kb.inline_keyboard:
            rows.extend(nav_kb.inline_keyboard)

        await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(rows))
    else:
        rows = []
        for p in slice_:
            rows.append([InlineKeyboardButton(f"📌 {p['title']}", callback_data=f"view:{p['id']}")])
        if nav_kb.inline_keyboard:
            rows.extend(nav_kb.inline_keyboard)
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows)
            )
        except BadRequest:
            pass


# ── Pagination callback ────────────────────────────────────────────────────────

async def paginate_posts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    page = int(query.data.split(":")[1])
    posts = context.user_data.get("posts_cache") or await get_posts(update.effective_user.id)
    await _render_posts_page(update, context, page=page, posts=posts, send_new=False)


# ── View single post ───────────────────────────────────────────────────────────

async def view_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    post_id = int(query.data.split(":")[1])
    post = await get_post(post_id, update.effective_user.id)

    if not post:
        await query.edit_message_text("Post not found.")
        return

    context.user_data["viewing_post_id"] = post_id
    text = _format_post_preview(post)
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=post_action_keyboard(post_id),
    )


def _format_post_preview(post: dict) -> str:
    lines = [f"📌 <b>{post['title']}</b>\n"]
    if post["media_type"]:
        lines.append(f"[{post['media_type'].upper()}]")
        if post["caption"]:
            lines.append(post["caption"])
    elif post["content"]:
        lines.append(post["content"])
    # show button count if any
    if post.get("buttons_json"):
        try:
            btn_rows = json.loads(post["buttons_json"])
            total = sum(len(r) for r in btn_rows)
            if total:
                lines.append(f"\n🔘 {total} button(s)")
        except Exception:
            pass
    lines.append(f"\n🕐 {post['created_at'][:16]}")
    return "\n".join(lines)


def _build_inline_kb(post: dict) -> InlineKeyboardMarkup | None:
    """Reconstruct InlineKeyboardMarkup from stored buttons_json."""
    raw = post.get("buttons_json")
    if not raw:
        return None
    try:
        btn_rows = json.loads(raw)
    except Exception:
        return None
    rows = []
    for row in btn_rows:
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


# ── Send post ──────────────────────────────────────────────────────────────────

async def send_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Sending…")
    post_id = int(query.data.split(":")[1])
    post = await get_post(post_id, update.effective_user.id)

    if not post:
        await query.edit_message_text("Post not found.")
        return

    chat_id = update.effective_chat.id
    bot = context.bot
    reply_markup = _build_inline_kb(post)

    try:
        if post["media_type"] == "photo":
            await bot.send_photo(
                chat_id, post["file_id"],
                caption=post["caption"] or None,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        elif post["media_type"] == "video":
            await bot.send_video(
                chat_id, post["file_id"],
                caption=post["caption"] or None,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        elif post["media_type"] == "document":
            await bot.send_document(
                chat_id, post["file_id"],
                caption=post["caption"] or None,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        else:
            await bot.send_message(
                chat_id,
                post["content"] or "(empty)",
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
    except Exception as e:
        await bot.send_message(chat_id, f"⚠️ Failed to send post: {e}")

    # Show back button
    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to post", callback_data=f"view:{post_id}")],
        ])
    )


# ── Delete post ────────────────────────────────────────────────────────────────

async def ask_delete_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    post_id = int(query.data.split(":")[1])
    post = await get_post(post_id, update.effective_user.id)
    title = post["title"] if post else "this post"
    await query.edit_message_text(
        f"🗑 Are you sure you want to delete <b>{title}</b>?",
        parse_mode="HTML",
        reply_markup=confirm_delete_keyboard(post_id),
    )


async def confirm_delete_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    post_id = int(query.data.split(":")[1])
    deleted = await delete_post(post_id, update.effective_user.id)

    if deleted:
        # Refresh cache
        posts = await get_posts(update.effective_user.id)
        context.user_data["posts_cache"] = posts
        await query.edit_message_text("✅ Post deleted.")
    else:
        await query.edit_message_text("⚠️ Could not delete post.")


async def cancel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    post_id = context.user_data.get("viewing_post_id")
    if post_id:
        post = await get_post(post_id, update.effective_user.id)
        if post:
            await query.edit_message_text(
                _format_post_preview(post),
                parse_mode="HTML",
                reply_markup=post_action_keyboard(post_id),
            )
            return
    await query.edit_message_text("Cancelled.")


# ── Edit post ──────────────────────────────────────────────────────────────────

async def show_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    post_id = int(query.data.split(":")[1])
    context.user_data["editing_post_id"] = post_id
    post = await get_post(post_id, update.effective_user.id)
    title = post["title"] if post else "Post"
    await query.edit_message_text(
        f"✏️ Editing: <b>{title}</b>\n\nWhat would you like to change?",
        parse_mode="HTML",
        reply_markup=edit_field_keyboard(post_id),
    )


async def ask_edit_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    post_id = int(query.data.split(":")[1])
    context.user_data["editing_post_id"] = post_id
    context.user_data["editing_field"] = "title"
    await query.message.reply_text(
        "📌 Send the new <b>title</b> for this post:",
        parse_mode="HTML",
        reply_markup=CANCEL_MENU,
    )
    return EDIT_WAITING_TITLE


async def ask_edit_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    post_id = int(query.data.split(":")[1])
    context.user_data["editing_post_id"] = post_id
    context.user_data["editing_field"] = "content"
    await query.message.reply_text(
        "📄 Send the new <b>content</b> for this post\n(text, photo, video, or document):",
        parse_mode="HTML",
        reply_markup=CANCEL_MENU,
    )
    return EDIT_WAITING_CONTENT


async def receive_edit_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_title = (update.message.text or "").strip()
    if not new_title:
        await update.message.reply_text("Title can't be empty.")
        return EDIT_WAITING_TITLE

    post_id = context.user_data.get("editing_post_id")
    post = await get_post(post_id, update.effective_user.id)
    if post:
        await update_post(
            post_id=post_id,
            user_id=update.effective_user.id,
            title=new_title,
            content=post["content"],
            media_type=post["media_type"],
            file_id=post["file_id"],
            caption=post["caption"],
            text_pos=post.get("text_pos", "below"),
            buttons_json=post.get("buttons_json"),
        )
    # Refresh cache
    context.user_data["posts_cache"] = await get_posts(update.effective_user.id)
    await update.message.reply_html("✅ Title updated!", reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def receive_edit_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    post_id = context.user_data.get("editing_post_id")
    post = await get_post(post_id, update.effective_user.id)
    if not post:
        await message.reply_text("Post not found.", reply_markup=MAIN_MENU)
        return ConversationHandler.END

    # Determine new content
    if message.photo:
        media_type, file_id, caption = "photo", message.photo[-1].file_id, message.caption or ""
        content = None
    elif message.video:
        media_type, file_id, caption = "video", message.video.file_id, message.caption or ""
        content = None
    elif message.document:
        media_type, file_id, caption = "document", message.document.file_id, message.caption or ""
        content = None
    else:
        media_type, file_id, caption = None, None, None
        content = message.text or ""

    await update_post(
        post_id=post_id,
        user_id=update.effective_user.id,
        title=post["title"],
        content=content,
        media_type=media_type,
        file_id=file_id,
        caption=caption,
        text_pos=post.get("text_pos", "below"),
        buttons_json=post.get("buttons_json"),
    )
    context.user_data["posts_cache"] = await get_posts(update.effective_user.id)
    await message.reply_html("✅ Content updated!", reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Edit cancelled.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def back_to_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    post_id = int(query.data.split(":")[1])
    post = await get_post(post_id, update.effective_user.id)
    if post:
        await query.edit_message_text(
            _format_post_preview(post),
            parse_mode="HTML",
            reply_markup=post_action_keyboard(post_id),
        )
    else:
        await query.edit_message_text("Post not found.")


# ── Build edit conversation handler ───────────────────────────────────────────

def build_edit_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ask_edit_title, pattern=r"^edit_title:\d+$"),
            CallbackQueryHandler(ask_edit_content, pattern=r"^edit_content:\d+$"),
        ],
        states={
            EDIT_WAITING_TITLE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex(r"^❌ Cancel$"),
                    receive_edit_title,
                ),
            ],
            EDIT_WAITING_CONTENT: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL)
                    & ~filters.COMMAND
                    & ~filters.Regex(r"^❌ Cancel$"),
                    receive_edit_content,
                ),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex(r"^❌ Cancel$"), cancel_edit),
        ],
        name="edit_post",
        persistent=False,
    )
