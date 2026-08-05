"""
Shared helper utilities.
"""
from telegram import Bot
from telegram.error import TelegramError
from bot.database.db import list_destinations, log_forward
from bot.config import FORWARD_MODE


async def forward_message_to_all(
    bot: Bot,
    from_chat_id: int | str,
    message_id: int,
) -> tuple[int, list[str]]:
    """
    Copy (or forward) a message to every configured destination.

    Returns
    -------
    (success_count, error_lines)
        success_count : number of destinations that received the message
        error_lines   : human-readable error descriptions for failed ones
    """
    destinations = await list_destinations()
    success = 0
    errors: list[str] = []

    for dest in destinations:
        dest_chat_id = dest["chat_id"]
        if str(dest_chat_id) == str(from_chat_id):
            continue
        try:
            if FORWARD_MODE == "copy":
                await bot.copy_message(
                    chat_id=dest_chat_id,
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                )
            else:
                await bot.forward_message(
                    chat_id=dest_chat_id,
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                )
            await log_forward(str(from_chat_id), message_id, dest_chat_id, "ok")
            success += 1
        except TelegramError as exc:
            err_line = f"- {dest['title']} ({dest_chat_id}): {exc.message}"
            errors.append(err_line)
            await log_forward(str(from_chat_id), message_id, dest_chat_id, "error")

    return success, errors


def build_forward_summary(success: int, total: int, errors: list[str]) -> str:
    """Return a human-readable summary string for the forward result."""
    text = f"Forwarded to {success}/{total} channel(s)."
    if errors:
        text += "\n\nFailed:\n" + "\n".join(errors)
    return text
