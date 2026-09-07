from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

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