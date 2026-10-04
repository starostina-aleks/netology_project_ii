from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

FEEDBACK_CB_PREFIX="fb"
FEEDBACK_UP="up"
FEEDBACK_DOWN="down"
FEEDBACK_VALUES=(FEEDBACK_UP,FEEDBACK_DOWN)


def topic_kb()->InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for slug,label in [
        ("ustav","Уставы"),
        ("doc_arm","Документация"),
        ("docs","Отчет")
        ]:
        builder.button(text=label,callback_data=f"topic:{slug}")
    builder.button(text="Отмена",callback_data="topic:cancel")
    builder.adjust(1)
    return builder.as_markup()

def feedback_kb(message_id:str)->InlineKeyboardMarkup:
    kb=InlineKeyboardBuilder()
    kb.button(
        text="👍",
        callback_data=f"{FEEDBACK_CB_PREFIX}:{FEEDBACK_UP}:{message_id}"
    )
    kb.button(
        text="👎",
        callback_data=f"{FEEDBACK_CB_PREFIX}:{FEEDBACK_DOWN}:{message_id}"
    )
    kb.adjust(2)
    return kb.as_markup()
