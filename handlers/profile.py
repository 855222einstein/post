"""Profile handler — show user stats."""
from telegram import Update
from telegram.ext import ContextTypes

from bot.db import upsert_user, get_user_stats
from bot.keyboards import MAIN_MENU


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await upsert_user(user.id, user.username, user.first_name)

    stats = await get_user_stats(user.id)
    if not stats:
        await update.message.reply_text("Couldn't load profile. Try again.", reply_markup=MAIN_MENU)
        return

    username_line = f"@{stats['username']}" if stats["username"] else "—"
    created = stats["created_at"][:10] if stats["created_at"] else "—"

    await update.message.reply_html(
        f"👤 <b>Your Profile</b>\n\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"📛 <b>Name:</b> {user.first_name}\n"
        f"🔗 <b>Username:</b> {username_line}\n"
        f"📅 <b>Joined:</b> {created}\n"
        f"📋 <b>Saved posts:</b> {stats['post_count']}",
        reply_markup=MAIN_MENU,
    )
