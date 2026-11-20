"""Inline-клавиатуры бота."""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import SERVICES, service_title


def services_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, item in SERVICES.items():
        builder.button(text=item["title"], callback_data=f"svc:{key}")
    builder.adjust(1)
    return builder.as_markup()


def admin_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="admin:stats")
    builder.button(text="👥 Клиенты", callback_data="admin:clients")
    builder.button(text="💬 Активные чаты", callback_data="admin:chats")
    builder.button(text="📋 Услуги и исполнители", callback_data="admin:services")
    builder.button(text="🧑‍💻 Как специалист", callback_data="admin:worker")
    builder.button(text="ℹ️ Инструкция", callback_data="admin:help")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def operator_kb(back_to_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Мои чаты", callback_data="opmenu:chats")
    builder.button(text="📈 Моя статистика", callback_data="opmenu:stats")
    builder.button(text="ℹ️ Инструкция", callback_data="opmenu:help")
    if back_to_admin:
        builder.button(text="👑 В админ-панель", callback_data="admin:back")
    builder.adjust(2, 1, 1) if back_to_admin else builder.adjust(2, 1)
    return builder.as_markup()


def chat_kb(chat_id: int, for_operator: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if for_operator:
        builder.button(text="✍️ Ответить", callback_data=f"op_reply:{chat_id}")
    builder.button(text="🔚 Завершить", callback_data=f"close:{chat_id}")
    builder.adjust(2 if for_operator else 1)
    return builder.as_markup()


def cancel_kb(chat_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data=f"cancel:{chat_id}")
    return builder.as_markup()


def chat_list_kb(chats, with_reply: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for chat in chats:
        label = f"💬 #{chat['id']} · {service_title(chat['service_key'])}"
        if with_reply:
            builder.button(text="✍️", callback_data=f"op_reply:{chat['id']}")
        builder.button(text=label, callback_data=f"noop:{chat['id']}")
        builder.button(text="🔚", callback_data=f"close:{chat['id']}")
    builder.adjust(3)
    return builder.as_markup()


def back_kb(target: str = "admin:back") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data=target)
    return builder.as_markup()
