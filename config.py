"""Конфигурация бота. Все секреты — через переменные окружения / .env."""
import json
import os
import re
import secrets

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
DB_PATH = os.getenv("DB_PATH", "data/bot.db")
PORT = int(os.getenv("PORT", "8080"))

# Telegram разрешает в secret token только A-Za-z0-9_- (до 256 символов).
# Render генерирует случайную строку с любыми символами — нормализуем её.
_raw_secret = os.getenv("WEBHOOK_SECRET", "").strip()
WEBHOOK_SECRET = re.sub(r"[^A-Za-z0-9_-]", "", _raw_secret)[:256]
if len(WEBHOOK_SECRET) < 16:
    WEBHOOK_SECRET = secrets.token_urlsafe(32)
WEBHOOK_PATH = "/webhook"
WEBHOOK_BASE = (
    os.getenv("WEBHOOK_URL")
    or os.getenv("RENDER_EXTERNAL_URL")
    or os.getenv("FLY_APP_URL")
    or ""
).rstrip("/")

# Услуги по умолчанию. В продакшене переопредели переменной SERVICES_JSON.
DEFAULT_SERVICES = [
    {"key": "site", "title": "🌐 Разработка сайта", "operator_id": ADMIN_ID or 0},
    {"key": "bot", "title": "🤖 Telegram-бот", "operator_id": 0},
    {"key": "design", "title": "🎨 Дизайн и вёрстка", "operator_id": 0},
]

_raw_services = os.getenv("SERVICES_JSON", "").strip()
try:
    _services_list = json.loads(_raw_services) if _raw_services else DEFAULT_SERVICES
except (ValueError, TypeError):
    _services_list = DEFAULT_SERVICES

SERVICES = {
    item["key"]: item
    for item in _services_list
    if isinstance(item, dict) and item.get("key") and item.get("title")
}

OPERATOR_IDS = set()
for item in _services_list:
    if isinstance(item, dict):
        raw_id = str(item.get("operator_id") or "").strip()
        if raw_id.isdigit() and int(raw_id) != ADMIN_ID:
            OPERATOR_IDS.add(int(raw_id))


def is_admin(user_id: int) -> bool:
    return bool(ADMIN_ID) and user_id == ADMIN_ID


def is_operator(user_id: int) -> bool:
    return is_admin(user_id) or user_id in OPERATOR_IDS


def role_for(user_id: int) -> str:
    if is_admin(user_id):
        return "admin"
    if is_operator(user_id):
        return "operator"
    return "client"


def service_title(key: str) -> str:
    item = SERVICES.get(key)
    return item["title"] if item else key


def operator_for(key: str) -> int:
    """Исполнитель услуги. Если не назначен — админ."""
    item = SERVICES.get(key) or {}
    raw_id = str(item.get("operator_id") or "").strip()
    operator_id = int(raw_id) if raw_id.isdigit() else 0
    return operator_id or ADMIN_ID


def operator_name(operator_id: int) -> str:
    if is_admin(operator_id):
        return "👑 ты (админ)"
    return f"🧑‍💻 {operator_id}"
