"""Telegram-бот для работы с клиентами: анонимный чат, услуги, админ-панель."""
import asyncio
import json
import re

from aiohttp import web

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import ai
import config
import database as db
from keyboards import (
    admin_kb,
    back_kb,
    cancel_kb,
    chat_kb,
    chat_list_kb,
    client_kb,
    history_kb,
    my_chats_kb,
    operator_kb,
    services_kb,
    spec_list_kb,
    spec_review_kb,
)

router = Router()


# ---------------------------------------------------------------- utils
def esc(value: str) -> str:
    """Экранируем только &, <, > — Telegram не любит числовые entity."""
    return (
        str(value)
        .replace("&", "&")
        .replace("<", "<")
        .replace(">", ">")
    )


def user_label(user) -> str:
    parts = []
    if user.full_name:
        parts.append(esc(user.full_name))
    if user.username:
        parts.append(f"@{esc(user.username)}")
    return " ".join(parts) or f"ID {user.id}"


def media_label(message: Message) -> str:
    if message.photo:
        return "[фото]"
    if message.video:
        return "[видео]"
    if message.voice:
        return "[голосовое]"
    if message.audio:
        return "[аудио]"
    if message.document:
        return "[файл]"
    if message.sticker:
        return "[стикер]"
    if message.location:
        return "[геолокация]"
    if message.contact:
        return "[контакт]"
    return "[сообщение]"


async def relay_to(bot: Bot, message: Message, target_id: int,
                   caption: str, markup) -> str:
    """Пересылаем сообщение, не раскрывая реальный аккаунт отправителя."""
    raw = (message.text or message.caption or "").strip()
    body = raw or media_label(message)
    prefix = f"{caption}\n\n{esc(raw)}" if raw else caption
    if len(prefix) > 1000:
        prefix = prefix[:997] + "…"

    try:
        if message.photo:
            await bot.send_photo(target_id, message.photo[-1].file_id,
                                 caption=prefix, reply_markup=markup)
        elif message.video:
            await bot.send_video(target_id, message.video.file_id,
                                 caption=prefix, reply_markup=markup)
        elif message.voice:
            await bot.send_voice(target_id, message.voice.file_id,
                                 caption=prefix, reply_markup=markup)
        elif message.audio:
            await bot.send_audio(target_id, message.audio.file_id,
                                 caption=prefix, reply_markup=markup)
        elif message.document:
            await bot.send_document(target_id, message.document.file_id,
                                    caption=prefix, reply_markup=markup)
        elif message.sticker:
            await bot.send_sticker(target_id, message.sticker.file_id,
                                   reply_markup=markup)
        elif message.location:
            await bot.send_location(target_id, message.location.latitude,
                                    message.location.longitude, reply_markup=markup)
        elif message.contact:
            await bot.send_contact(target_id, message.contact.phone_number,
                                   message.contact.first_name, reply_markup=markup)
        else:
            await bot.send_message(target_id, prefix, reply_markup=markup)
    except TelegramBadRequest as exc:
        await bot.send_message(
            target_id,
            f"{caption}\n\n⚠️ Не удалось переслать вложение ({exc.message[:80]}).",
            reply_markup=markup,
        )
    return body


async def safe_edit(target: Message, text: str, markup=None) -> None:
    try:
        await target.edit_text(text[:4096], reply_markup=markup)
    except TelegramBadRequest:
        await target.answer(text[:4096], reply_markup=markup)


async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs) -> None:
    """Уведомление не должно ронять весь webhook, если адресат заблокировал бота."""
    try:
        await bot.send_message(chat_id, text, **kwargs)
    except TelegramAPIError as exc:
        print(f"⚠️ Не удалось уведомить {chat_id}: {exc}", flush=True)


def fmt_date(iso: str) -> str:
    return iso[:10] if iso else "—"


def get_my_commands(role: str) -> list:
    """Возвращает список команд для роли пользователя."""
    cmds = {
        "admin": [
            ("admin", "👑 Админ-панель"),
            ("/id", "🆔 Мой ID"),
            ("/start", "🔙 Начало"),
            ("/help", "ℹ️ Помощь"),
        ],
        "operator": [
            ("/mychats", "📁 Мои заказы"),
            ("/start", "🔙 Начало"),
            ("/help", "ℹ️ Помощь"),
        ],
        "client": [
            ("/mychats", "📁 Мои заказы"),
            ("/start", "🔙 Начало"),
            ("/help", "ℹ️ Помощь"),
        ],
    }
    return cmds.get(role, cmds["client"])


# ---------------------------------------------------------------- panels

async def show_services(target: Message, client_id: int) -> None:
    active = await db.get_active_chat_for_client(client_id)
    if active:
        text = (
            f"👋 У тебя активный заказ #{active['id']}.\n"
            "Просто напиши сообщение или ответь на сообщение специалиста — "
            "оно уйдёт в этот же чат.\n\n"
            "ВсеPrevious заказы и переписка — в разделе «📁 Мои заказы»."
        ).replace("Previous", "прошлые")
        await target.answer(text, reply_markup=client_kb(active["id"]))
        return
    await target.answer(
        "👋 Привет! Я бот студии retr1kze.\n\n"
        "Выбери услугу — и я анонимно свяжу тебя со специалистом. "
        "Твой Telegram не будет виден.\n\n"
        "Раньше писал нам? Открой «📁 Мои заказы» — там вся история переписки.",
        reply_markup=services_kb(),
    )


async def show_admin_panel(target: Message, edit: bool = False) -> None:
    text = (
        "👑 <b>Админ-панель</b>\n\n"
        "Здесь видно всех клиентов, чаты и статистику.\n"
        "Специалисты видят только свои чаты.\n\n"
        "Выбери раздел:"
    )
    if edit:
        await safe_edit(target, text, admin_kb())
    else:
        await target.answer(text, reply_markup=admin_kb())


async def show_operator_panel(target: Message, edit: bool = False,
                              back_to_admin: bool = False) -> None:
    text = (
        "🧑‍💻 <b>Панель специалиста</b>\n\n"
        "Клиенты, выбравшие твои услуги, попадают сюда.\n"
        "Отвечать можно кнопкой «Ответить» в чате с ботом.\n\n"
        "Выбери раздел:"
    )
    markup = operator_kb(back_to_admin=back_to_admin)
    if edit:
        await safe_edit(target, text, markup)
    else:
        await target.answer(text, reply_markup=markup)


async def show_my_chats(target: Message, user_id: int) -> None:
    """Показать список заказов клиента."""
    chats = await db.get_client_chats(user_id)
    text = "📁 <b>Твои заказы</b>\n"
    if not chats:
        text += "Пока заказов нет."
    else:
        for chat in chats:
            mark = "🟢" if chat["status"] == "active" else "✅"
            text += (
                f"\n{mark} #{chat['id']} · "
                f"{config.service_title(chat['service_key'])} · "
                f"{fmt_date(chat['created_at'])}"
            )
    await target.answer(text, reply_markup=my_chats_kb(chats))


async def show_history(target: Message, chat_id: int, user_id: int) -> None:
    """Показать историю конкретного чата."""
    chat = await db.get_chat(chat_id)
    if not chat or chat["client_id"] != user_id:
        await target.answer("Заказ не найден", show_alert=True)
        return

    messages = await db.get_chat_messages(chat_id)
    lines = [
        f"📄 <b>Заказ #{chat_id}</b> · {config.service_title(chat['service_key'])} · "
        f"{chat['status']} · {fmt_date(chat['created_at'])}\n"
    ]
    for item in messages:
        who = "Ты" if item["sender_id"] == user_id else "Специалист"
        body = esc(item["body"] or "")
        if len(body) > 300:
            body = body[:297] + "…"
        lines.append(f"{who}: {body}")
    is_active = chat["status"] == "active"
    await target.answer(
        "\n".join(lines),
        reply_markup=history_kb(chat_id, is_active),
    )


# ---------------------------------------------------------------- commands
@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    role = config.role_for(user.id)
    await db.register_user(user.id, user.username, user.full_name, role)
    await db.log("start", user.id)

    # Устанавливаем команды бота (появляются при вводе /)
    try:
        bot = Bot(config.BOT_TOKEN)
        role = config.role_for(user.id)
        cmds = get_my_commands(role)
        await bot.set_my_commands(cmds, language_code="en")
    except Exception:
        pass  # Не критично, если не получится

    if role == "admin":
        await show_admin_panel(message)
    elif role == "operator":
        await show_operator_panel(message)
    else:
        await show_services(message, user.id)


@router.message(Command("help"))
async def cmd_help(message: Message):
    user = message.from_user
    role = config.role_for(user.id)
    if role == "admin":
        text = (
            "ℹ️ <b>Инструкция для админа</b>\n\n"
            "• Клиент заходит по ссылке на бота, жмёт /start и выбирает услугу.\n"
            "• Бот назначает специалиста по услуге и открывает анонимный чат.\n"
            "• Специалист отвечает кнопкой «Ответить».\n"
            "• Друзья получают доступ только к своим чатам.\n"
            "• Админ-панель доступна только тебе.\n\n"
            "Чтобы добавить друга: узнай его ID командой /id и укажи в SERVICES_JSON.\n\n"
            "Команды при вводе /:\n"
        )
        for cmd, desc in [
            ("admin", "👑 Админ-панель"),
            ("/id", "🆔 Мой ID"),
            ("/start", "🔙 Начало"),
            ("/help", "ℹ️ Помощь"),
        ]:
            text += f"• {cmd} — {desc}\n"
        await message.answer(text, parse_mode="HTML")
    elif role == "operator":
        text = (
            "ℹ️ <b>Инструкция для специалиста</b>\n\n"
            "1. В чате с ботом придёт уведомление о новом клиенте.\n"
            "2. Нажми «Ответить» и напиши сообщение.\n"
            "3. Клиент получит его анонимно.\n"
            "4. «Завершить» — закрыть диалог.\n\n"
            "Ты видишь только клиентов своих услуг. Админ видит всё.\n\n"
            "Команды при вводе /:\n"
        )
        for cmd, desc in [
            ("/mychats", "📁 Мои заказы"),
            ("/start", "🔙 Начало"),
            ("/help", "ℹ️ Помощь"),
        ]:
            text += f"• {cmd} — {desc}\n"
        await message.answer(text, parse_mode="HTML")
    else:
        text = (
            "ℹ️ <b>Инструкция для клиента</b>\n\n"
            "1. Нажми /start и выбери услугу.\n"
            "2. Бот свяжет тебя со специалистом анонимно.\n"
            "3. Пиши сообщения — специалист получит их.\n"
            "4. Чтобы вернуться к диалогу: используй команду /mychats\n"
            "5. Чтобы завершить чат: нажми «🔚 Завершить»\n\n"
            "Команды при вводе /:\n"
        )
        for cmd, desc in [
            ("/mychats", "📁 Мои заказы"),
            ("/start", "🔙 Начало"),
            ("/help", "ℹ️ Помощь"),
        ]:
            text += f"• {cmd} — {desc}\n"
        await message.answer(text, parse_mode="HTML")


@router.message(Command("id"))
async def cmd_id(message: Message):
    await db.register_user(
        message.from_user.id, message.from_user.username,
        message.from_user.full_name, config.role_for(message.from_user.id),
    )
    role = config.role_for(message.from_user.id)
    await message.answer(
        f"🆔 Твой Telegram ID: <code>{message.from_user.id}</code>\n"
        f"Роль: <b>{role}</b>\n\n"
        "Отправь этот ID администратору, чтобы тебя добавили как специалиста."
    )


@router.message(Command("mychats"))
async def cmd_mychats(message: Message):
    user = message.from_user
    role = config.role_for(user.id)
    if role != "client":
        await message.answer("Эта команда доступна только клиентам.")
        return
    await show_my_chats(message, user.id)


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not config.is_admin(message.from_user.id):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return
    await show_admin_panel(message)


# ---------------------------------------------------------------- callbacks
@router.callback_query(F.data.startswith("svc:"))
async def cb_service(callback: CallbackQuery):
    key = callback.data.split(":", 1)[1]
    service = config.SERVICES.get(key)
    if not service:
        await callback.answer("Услуга не найдена", show_alert=True)
        return

    user = callback.from_user
    await db.register_user(user.id, user.username, user.full_name, "client")

    active = await db.get_active_chat_for_client(user.id)
    if active:
        await safe_edit(callback.message, "У тебя уже есть активный чат.",
                        chat_kb(active["id"], for_operator=False))
        await callback.answer()
        return

    operator_id = config.operator_for(key)
    chat_id = await db.create_chat(user.id, operator_id, key)
    await db.log("service_selected", user.id, chat_id, key)

    await safe_edit(
        callback.message,
        f"✅ Ты выбрал: <b>{esc(service['title'])}</b>\n\n"
        "Напиши задачу — специалист получит её и ответит сюда. "
        "Твой Telegram ему не виден.",
        chat_kb(chat_id, for_operator=False),
    )

    await safe_send(
        callback.bot,
        operator_id,
        f"🆕 <b>Новый чат #{chat_id}</b>\n"
        f"Услуга: {esc(service['title'])}\n"
        f"Клиент: анонимно (чат #{chat_id})\n\n"
        "Нажми «Ответить», чтобы написать ему.",
        reply_markup=chat_kb(chat_id, for_operator=True),
    )
    if operator_id != config.ADMIN_ID:
        await safe_send(
            callback.bot,
            config.ADMIN_ID,
            f"📥 Новый клиент у специалиста {operator_id}: "
            f"{esc(service['title'])} · чат #{chat_id}\n"
            f"Клиент: {user_label(user)} (ID {user.id})",
        )
    await callback.answer("Специалист уведомлён")


@router.callback_query(F.data.startswith("op_reply:"))
async def cb_reply(callback: CallbackQuery):
    chat_id = int(callback.data.split(":", 1)[1])
    chat = await db.get_chat(chat_id)
    if not chat or chat["status"] != "active":
        await callback.answer("Чат уже закрыт", show_alert=True)
        return
    uid = callback.from_user.id
    if not (config.is_admin(uid) or chat["operator_id"] == uid):
        await callback.answer("Это не твой чат ⛔", show_alert=True)
        return

    # Получаем последнее сообщение из чата, чтобы показать контекст
    messages = await db.get_chat_messages(chat_id, limit=1)
    last_msg = messages[0]["body"] if messages else ""

    await db.set_pending(uid, chat_id)
    await safe_edit(
        callback.message,
        f"✍️ Введи ответ для клиента (чат #{chat_id}).\n\n"
        f"💬 Откликаешься на: {last_msg}\n\n"
        "Можно отправить текст, фото, файл или голосовое.",
        cancel_kb(chat_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(callback: CallbackQuery):
    await db.clear_pending(callback.from_user.id)
    await safe_edit(callback.message, "Отменено.",
                    operator_kb(back_to_admin=config.is_admin(callback.from_user.id)))
    await callback.answer()


@router.callback_query(F.data.startswith("close:"))
async def cb_close(callback: CallbackQuery):
    chat_id = int(callback.data.split(":", 1)[1])
    chat = await db.get_chat(chat_id)
    if not chat:
        await callback.answer("Чат не найден", show_alert=True)
        return
    uid = callback.from_user.id
    if not (config.is_admin(uid) or chat["operator_id"] == uid
            or chat["client_id"] == uid):
        await callback.answer("Недостаточно прав ⛔", show_alert=True)
        return

    await db.close_chat(chat_id)
    pending = await db.get_pending(chat["operator_id"])
    if pending == chat_id:
        await db.clear_pending(chat["operator_id"])

    for target_id, text in (
        (chat["client_id"], "🔚 Чат завершён. Спасибо, что написал! Если появятся вопросы — нажми /start."),
        (chat["operator_id"], f"🔚 Чат #{chat_id} завершён."),
    ):
        if target_id != uid:
            await safe_send(callback.bot, target_id, text)

    await db.log("chat_closed", uid, chat_id, chat["service_key"])
    await safe_edit(callback.message, f"✅ Чат #{chat_id} завершён.")
    await callback.answer("Чат закрыт")


@router.callback_query(F.data.startswith("noop:"))
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("opmenu:"))
async def cb_operator_menu(callback: CallbackQuery):
    uid = callback.from_user.id
    if not config.is_operator(uid):
        await callback.answer("⛔ Доступно только специалистам", show_alert=True)
        return
    action = callback.data.split(":", 1)[1]

    if action == "chats":
        chats = await db.get_active_chats(uid)
        if not chats:
            await safe_edit(callback.message, "💬 Пока нет активных чатов.",
                            back_kb("admin:worker" if config.is_admin(uid) else "opmenu:back"))
        else:
            lines = ["💬 <b>Мои активные чаты</b>\n"]
            for chat in chats:
                lines.append(
                    f"• #{chat['id']} · {config.service_title(chat['service_key'])} "
                    f"· клиент {chat['client_id']} · {fmt_date(chat['created_at'])}"
                )
            await safe_edit(callback.message, "\n".join(lines), chat_list_kb(chats))
    elif action == "stats":
        stats = await db.get_operator_stats(uid)
        text = (
            "📈 <b>Моя статистика</b>\n\n"
            f"Всего чатов: <b>{stats['chats']}</b>\n"
            f"Активных сейчас: <b>{stats['active']}</b>\n"
            f"Отправлено ответов: <b>{stats['replies']}</b>"
        )
        await safe_edit(callback.message, text,
                        back_kb("admin:worker" if config.is_admin(uid) else "opmenu:back"))
    elif action == "help":
        await safe_edit(
            callback.message,
            "ℹ️ <b>Как работать</b>\n\n"
            "1. В чате с ботом придёт уведомление о новом клиенте.\n"
            "2. Нажми «Ответить» и напиши сообщение.\n"
            "3. Клиент получит его анонимно.\n"
            "4. «Завершить» — закрыть диалог.\n\n"
            "Ты видишь только клиентов своих услуг. Админ видит всё.",
            back_kb("admin:worker" if config.is_admin(uid) else "opmenu:back"),
        )
    else:
        await show_operator_panel(callback.message, edit=True,
                                  back_to_admin=config.is_admin(uid))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:"))
async def cb_admin(callback: CallbackQuery):
    if not config.is_admin(callback.from_user.id):
        await callback.answer("⛔ Только для администратора", show_alert=True)
        return
    action = callback.data.split(":", 1)[1]

    if action == "back":
        await show_admin_panel(callback.message, edit=True)
    elif action == "worker":
        await show_operator_panel(callback.message, edit=True, back_to_admin=True)
    elif action == "help":
        await safe_edit(
            callback.message,
            "ℹ️ <b>Инструкция</b>\n\n"
            "• Клиент заходит по ссылке на бота, жмёт /start и выбирает услугу.\n"
            "• Бот назначает специалиста по услуге и открывает анонимный чат.\n"
            "• Специалист отвечает кнопкой «Ответить».\n"
            "• Друзья получают доступ только к своим чатам.\n"
            "• Админ-панель доступна только тебе.\n\n"
            "Чтобы добавить друга: узнай его ID командой /id и укажи в SERVICES_JSON.",
            admin_kb(),
        )
    elif action == "stats":
        stats = await db.get_stats()
        lines = [
            "📊 <b>Статистика</b>",
            "",
            f"👥 Клиентов всего: <b>{stats['clients']}</b>",
            f"🆕 Новых сегодня: <b>{stats['clients_today']}</b>",
            f"💬 Чатов всего: <b>{stats['chats']}</b>",
            f"🟢 Активных чатов: <b>{stats['chats_active']}</b>",
            f"📨 Сообщений: <b>{stats['messages']}</b>",
            f"📅 Сообщений сегодня: <b>{stats['messages_today']}</b>",
            "",
            "<b>По услугам:</b>",
        ]
        for row in stats["services"]:
            lines.append(f"• {config.service_title(row['service_key'])} — {row['cnt']}")
        if not stats["services"]:
            lines.append("• пока нет")
        lines += ["", "<b>По специалистам:</b>"]
        for row in stats["operators"]:
            lines.append(f"• {config.operator_name(row['operator_id'])} — {row['cnt']}")
        if not stats["operators"]:
            lines.append("• пока нет")
        lines += ["", f"🧠 <b>ТЗ на проверке:</b> {stats['pending_specs']}"]
        await safe_edit(callback.message, "\n".join(lines), back_kb())
    elif action == "specs":
        specs = await db.get_pending_specs()
        if not specs:
            await safe_edit(callback.message, "📄 Нет ТЗ на проверке.", back_kb())
        else:
            await safe_edit(
                callback.message, "📄 <b>ТЗ на проверке</b>", spec_list_kb(specs)
            )
    elif action == "clients":
        stats = await db.get_stats()
        lines = ["👥 <b>Последние клиенты</b>\n"]
        for row in stats["recent_clients"]:
            name = esc(row["full_name"] or row["username"] or "без имени")
            service = esc(config.service_title(row["last_service"])) if row["last_service"] else "—"
            lines.append(f"• <code>{row['id']}</code> {name} · {service} · {fmt_date(row['created_at'])}")
        if len(lines) == 1:
            lines.append("Пока нет клиентов.")
        await safe_edit(callback.message, "\n".join(lines), back_kb())
    elif action == "chats":
        chats = await db.get_active_chats()
        if not chats:
            await safe_edit(callback.message, "💬 Активных чатов нет.", back_kb())
        else:
            lines = ["💬 <b>Активные чаты</b>\n"]
            for chat in chats:
                lines.append(
                    f"• #{chat['id']} · {config.service_title(chat['service_key'])} "
                    f"· 👉 {config.operator_name(chat['operator_id'])}"
                )
            await safe_edit(callback.message, "\n".join(lines), chat_list_kb(chats))
    elif action == "services":
        lines = ["📋 <b>Услуги и исполнители</b>\n"]
        for key, item in config.SERVICES.items():
            target = config.operator_for(key)
            lines.append(f"• {config.service_title(item['title'])} → {config.operator_name(target)}")
        if not config.SERVICES:
            lines.append("Услуги не настроены.")
        await safe_edit(callback.message, "\n".join(lines), back_kb())
    else:
        await show_admin_panel(callback.message, edit=True)

    await callback.answer()


# ---------------------------------------------------------------- сообщения
@router.message()
async def handle_message(message: Message):
    user = message.from_user
    uid = user.id
    text = (message.text or "").strip()
    role = config.role_for(uid)
    await db.register_user(uid, user.username, user.full_name, role)

    if text.startswith("/"):
        # Обработка команд, введенных в поле ввода
        if text == "/start":
            await cmd_start(message)
        elif text == "/help":
            await cmd_help(message)
        elif text == "/id":
            await cmd_id(message)
        elif text == "/mychats":
            await cmd_mychats(message)
        elif text == "/admin":
            await cmd_admin(message)
        else:
            await message.answer("Неизвестная команда. Напиши /start, чтобы открыть меню.")
        return

    # отмена режима ответа
    if text == "❌ Отмена":
        if await db.get_pending(uid):
            await db.clear_pending(uid)
            await message.answer("Отменено.",
                                 reply_markup=operator_kb(back_to_admin=config.is_admin(uid)))
        return

    # специалист отвечает клиенту
    if config.is_operator(uid):
        pending = await db.get_pending(uid)
        if pending:
            chat = await db.get_chat(pending)
            if chat and chat["status"] == "active":
                # Получаем последнее сообщение для контекста
                messages = await db.get_chat_messages(chat["id"], limit=1)
                original = messages[0]["body"] if messages else ""

                body = await relay_to(
                    message.bot, message, chat["client_id"],
                    "💬 <b>Ответ специалиста</b>",
                    chat_kb(chat["id"], for_operator=False),
                )
                await db.save_message(chat["id"], uid, "op_to_client", body)
                await db.log("operator_reply", uid, chat["id"], chat["service_key"])
                await db.clear_pending(uid)
                await message.answer("✅ Ответ отправлен клиенту.")
                return
            await db.clear_pending(uid)

    # клиент пишет специалисту
    active = await db.get_active_chat_for_client(uid)
    if active:
        title = config.service_title(active["service_key"])
        body = await relay_to(
            message.bot, message, active["operator_id"],
            f"💬 <b>Клиент #{active['id']} · {title}</b>",
            chat_kb(active["id"], for_operator=True),
        )
        await db.save_message(active["id"], uid, "client_to_op", body)
        await db.log("client_message", uid, active["id"], active["service_key"])
        await message.answer("✅ Сообщение отправлено специалисту.")
        return

    # просто меню
    if role == "admin":
        await show_admin_panel(message)
    elif role == "operator":
        await show_operator_panel(message)
    else:
        await show_services(message, uid)


# ---------------------------------------------------------------- entrypoint
def validate_config() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit("❌ Не задан BOT_TOKEN. Скопируй .env.example в .env и заполни его.")
    if not config.ADMIN_ID:
        raise SystemExit("❌ Не задан ADMIN_ID — без него админ-панель недоступна.")
    if not config.SERVICES:
        raise SystemExit("❌ Не настроены услуги (SERVICES_JSON).")


def build_bot() -> tuple[Bot, Dispatcher]:
    """Создаём объекты синхронно: aiohttp-сессия Bot ленивая и привяжене
    к тому event loop, в котором реально запустится приложение."""
    validate_config()
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return bot, dispatcher


async def run_polling() -> None:
    bot, dispatcher = build_bot()
    await db.init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Режим polling (локальный тест)")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def run_webhook() -> None:
    """web.run_app() сам создаёт event loop, поэтому эту функцию НЕЛЬЗЯ
    вызывать из asyncio.run() — иначе объекты окажутся в разных loop'ах."""
    bot, dispatcher = build_bot()
    webhook_url = f"{config.WEBHOOK_BASE}{config.WEBHOOK_PATH}"

    async def on_startup(dispatcher: Dispatcher) -> None:
        await db.init_db()
        # Не дропаем pending: если Free-сервис Render спал, Telegram
        # успел накопить сообщения — они должны дойти после просыпания.
        await bot.set_webhook(
            webhook_url,
            secret_token=config.WEBHOOK_SECRET,
            drop_pending_updates=False,
        )
        print(f"✅ Webhook: {webhook_url}", flush=True)

    async def on_shutdown(dispatcher: Dispatcher) -> None:
        await bot.session.close()

    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)

    application = web.Application()
    application.router.add_get("/", lambda request: web.Response(text="bot is alive"))
    SimpleRequestHandler(
        dispatcher=dispatcher, bot=bot, secret_token=config.WEBHOOK_SECRET
    ).register(application, path=config.WEBHOOK_PATH)
    setup_application(application, dispatcher, bot=bot)
    web.run_app(application, host="0.0.0.0", port=config.PORT)


if __name__ == "__main__":
    if config.WEBHOOK_BASE:
        run_webhook()
    else:
        asyncio.run(run_polling())