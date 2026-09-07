from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class SubAction(CallbackData, prefix="sub"):
    # accept | reject | done  ("done" = inert button on an already-handled card)
    action: str
    sub_id: int


def moderation_kb(sub_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=SubAction(action="accept", sub_id=sub_id))
    kb.button(text="❌ Отклонить", callback_data=SubAction(action="reject", sub_id=sub_id))
    kb.adjust(2)
    return kb.as_markup()


def decided_kb(label: str, sub_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=label, callback_data=SubAction(action="done", sub_id=sub_id))
    kb.adjust(1)
    return kb.as_markup()
