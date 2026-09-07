from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class SubAction(CallbackData, prefix="sub"):
    # accept | reject | done  ("done" = inert button on an already-handled card)
    action: str
    sub_id: int


class CircleAction(CallbackData, prefix="circle"):
    # del | restore
    action: str
    circle_id: int


def moderation_kb(sub_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=SubAction(action="accept", sub_id=sub_id))
    kb.button(text="❌ Отклонить", callback_data=SubAction(action="reject", sub_id=sub_id))
    kb.adjust(2)
    return kb.as_markup()


def _circle_button(circle_id: int, *, active: bool) -> InlineKeyboardButton:
    if active:
        return InlineKeyboardButton(
            text="🗑 Удалить кружок",
            callback_data=CircleAction(action="del", circle_id=circle_id).pack(),
        )
    return InlineKeyboardButton(
        text="♻️ Вернуть кружок",
        callback_data=CircleAction(action="restore", circle_id=circle_id).pack(),
    )


def circle_row_kb(circle_id: int, *, active: bool) -> InlineKeyboardMarkup:
    """Single 🗑 / ♻️ button — used under each circle in the ``/circles`` gallery."""
    return InlineKeyboardMarkup(inline_keyboard=[[_circle_button(circle_id, active=active)]])


def decided_kb(
    label: str,
    *,
    sub_id: int,
    circle_id: int | None = None,
    circle_active: bool = True,
) -> InlineKeyboardMarkup:
    """Finalised moderation card: an inert label row, plus a 🗑/♻️ row for accepted circles."""
    label_btn = InlineKeyboardButton(
        text=label, callback_data=SubAction(action="done", sub_id=sub_id).pack()
    )
    rows: list[list[InlineKeyboardButton]] = [[label_btn]]
    if circle_id is not None:
        rows.append([_circle_button(circle_id, active=circle_active)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def flip_circle_buttons(
    markup: InlineKeyboardMarkup | None,
    circle_id: int,
    *,
    now_active: bool,
) -> InlineKeyboardMarkup | None:
    """Return a copy of ``markup`` with any ``CircleAction`` button for ``circle_id``
    swapped to the 🗑/♻️ state matching ``now_active``. Other buttons are untouched.

    ``markup is None`` -> ``None``. No matching button -> the markup is returned
    effectively unchanged (``edit_reply_markup`` then yields "message is not
    modified", which callers suppress).
    """
    if markup is None:
        return None
    new_rows: list[list[InlineKeyboardButton]] = []
    for row in markup.inline_keyboard:
        new_row: list[InlineKeyboardButton] = []
        for btn in row:
            parsed = None
            if btn.callback_data:
                try:
                    parsed = CircleAction.unpack(btn.callback_data)
                except (TypeError, ValueError):
                    parsed = None
            if parsed is not None and parsed.circle_id == circle_id:
                new_row.append(_circle_button(circle_id, active=now_active))
            else:
                new_row.append(btn)
        new_rows.append(new_row)
    return InlineKeyboardMarkup(inline_keyboard=new_rows)
