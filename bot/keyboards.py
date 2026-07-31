"""Reusable keyboard layouts."""
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

# ── Start inline keyboard ──────────────────────────────────────────────────────

START_INLINE_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("Create", callback_data="create:new")],
])

# ── Main menu (persistent reply keyboard) ──────────────────────────────────────

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["📝 Create post"],
        ["📋 My posts", "👤 Profile"],
    ],
    resize_keyboard=True,
    input_field_placeholder="Choose an action…",
)

CANCEL_MENU = ReplyKeyboardMarkup(
    [["❌ Cancel"]],
    resize_keyboard=True,
)

BACK_TO_POST_MENU = ReplyKeyboardMarkup(
    [["🔙 Back to post"]],
    resize_keyboard=True,
)


def post_settings_keyboard(text_pos: str = "below") -> ReplyKeyboardMarkup:
    """Post-settings menu shown while editing a draft."""
    pos_label = "⬇️ Text: BELOW" if text_pos == "below" else "⬆️ Text: ABOVE"
    return ReplyKeyboardMarkup(
        [
            ["Add text", "Add buttons"],
            [pos_label],
            ["✅ Done", "❌ Cancel"],
        ],
        resize_keyboard=True,
    )


# ── Inline helpers ─────────────────────────────────────────────────────────────

def post_action_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """Inline buttons shown under each saved post."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 Send", callback_data=f"send:{post_id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit:{post_id}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{post_id}"),
        ]
    ])


def confirm_delete_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, delete", callback_data=f"confirm_delete:{post_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_delete"),
        ]
    ])


def posts_navigation_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Pagination row for the posts list."""
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page:{page - 1}"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page:{page + 1}"))
    return InlineKeyboardMarkup([buttons]) if buttons else InlineKeyboardMarkup([])


def edit_field_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """Choose what to edit inside a post."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📌 Title", callback_data=f"edit_title:{post_id}"),
            InlineKeyboardButton("📄 Content", callback_data=f"edit_content:{post_id}"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data=f"back_to_post:{post_id}")],
    ])
