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
    builder.button(text="📄 ТЗ на проверке", callback_data="admin:specs")
    builder.button(text="🧑‍💻 Как специалист", callback_data="admin:worker")
    builder.button(text="ℹ️ Инструкция", callback_data="admin:help")
    builder.adjust(2, 2, 2, 1)
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
        builder.button(text="🧠 Собрать ТЗ", callback_data=f"spec:{chat_id}")
    builder.button(text="🔚 Завершить", callback_data=f"close:{chat_id}")
    builder.adjust(2, 1) if for_operator else builder.adjust(1)
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


def client_kb(active_chat_id: int | None = None) -> InlineKeyboardMarkup:
    """Главное меню клиента: история заказов всегда под рукой."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📁 Мои заказы", callback_data="client:chats")
    builder.button(text="🆕 Новый заказ", callback_data="client:services")
    if active_chat_id:
        builder.button(text="🔚 Завершить", callback_data=f"close:{active_chat_id}")
    builder.adjust(2, 1) if active_chat_id else builder.adjust(2)
    return builder.as_markup()


def my_chats_kb(chats) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for chat in chats:
        mark = "🟢" if chat["status"] == "active" else "✅"
        label = f"{mark} #{chat['id']} · {service_title(chat['service_key'])}"
        builder.button(text=label, callback_data=f"history:{chat['id']}")
    builder.button(text="🆕 Новый заказ", callback_data="client:services")
    builder.button(text="🔙 В меню", callback_data="client:menu")
    builder.adjust(1, 2)
    return builder.as_markup()


def history_kb(chat_id: int, is_active: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not is_active:
        builder.button(text="✉️ Продолжить", callback_data=f"reopen:{chat_id}")
    builder.button(text="🆕 Новый заказ", callback_data="client:services")
    builder.button(text="🔙 Мои заказы", callback_data="client:chats")
    builder.adjust(2, 1) if not is_active else builder.adjust(2)
    return builder.as_markup()


def spec_review_kb(spec_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Принять", callback_data=f"spec_review:{spec_id}:approve")
    builder.button(text="❌ Отклонить", callback_data=f"spec_review:{spec_id}:reject")
    builder.button(text="📄 Все ТЗ", callback_data="admin:specs")
    builder.adjust(2, 1)
    return builder.as_markup()


def spec_list_kb(specs) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for spec in specs:
        builder.button(
            text=f"📄 ТЗ #{spec['id']} · чат #{spec['chat_id']}",
            callback_data=f"spec_open:{spec['id']}",
        )
    builder.button(text="🔙 Назад", callback_data="admin:back")
    builder.adjust(1)
    return builder.as_markup()


def back_kb(target: str = "admin:back") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data=target)
    return builder.as_markup()
