from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from circlebot.keyboards import (
    CircleAction,
    SubAction,
    circle_row_kb,
    decided_kb,
    flip_circle_buttons,
)


def test_circle_row_kb_active_and_inactive() -> None:
    active = circle_row_kb(5, active=True).inline_keyboard[0][0]
    assert "🗑" in active.text
    assert CircleAction.unpack(active.callback_data) == CircleAction(action="del", circle_id=5)

    inactive = circle_row_kb(5, active=False).inline_keyboard[0][0]
    assert "♻️" in inactive.text
    assert CircleAction.unpack(inactive.callback_data).action == "restore"


def test_decided_kb_row_count() -> None:
    assert len(decided_kb("✅ Принято", sub_id=1).inline_keyboard) == 1
    two = decided_kb("✅ Принято", sub_id=1, circle_id=7)
    assert len(two.inline_keyboard) == 2
    assert CircleAction.unpack(two.inline_keyboard[1][0].callback_data).circle_id == 7

    inactive = decided_kb("✅ Принято", sub_id=1, circle_id=7, circle_active=False)
    assert "♻️" in inactive.inline_keyboard[1][0].text


def test_flip_toggles_only_the_matching_circle_button() -> None:
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Принято · Kirill",
                callback_data=SubAction(action="done", sub_id=1).pack(),
            )],
            [InlineKeyboardButton(
                text="🗑 Удалить кружок",
                callback_data=CircleAction(action="del", circle_id=7).pack(),
            )],
        ]
    )

    flipped = flip_circle_buttons(markup, 7, now_active=False)
    assert flipped.inline_keyboard[0][0].text == "✅ Принято · Kirill"  # label row untouched
    assert flipped.inline_keyboard[0][0].callback_data == SubAction(action="done", sub_id=1).pack()
    assert "♻️" in flipped.inline_keyboard[1][0].text
    assert CircleAction.unpack(flipped.inline_keyboard[1][0].callback_data).action == "restore"

    back = flip_circle_buttons(flipped, 7, now_active=True)
    assert "🗑" in back.inline_keyboard[1][0].text


def test_flip_ignores_other_circle_ids() -> None:
    markup = circle_row_kb(7, active=True)
    unchanged = flip_circle_buttons(markup, 999, now_active=False)
    assert unchanged.inline_keyboard[0][0].text == markup.inline_keyboard[0][0].text


def test_flip_handles_none() -> None:
    assert flip_circle_buttons(None, 1, now_active=True) is None
