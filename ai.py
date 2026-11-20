"""Сбор ТЗ из переписки через бесплатный Gemini API.

Используем прямой REST-вызов через aiohttp — без тяжёлого SDK и без
дополнительных зависимостей, несовместимых с Python 3.14 на Render.
"""
import aiohttp

import config

URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)

SYSTEM_PROMPT = """Ты ассистент студии retr1kze. Из переписки клиента и специалиста
собери короткое, но полное техническое задание на русском языке.

Правила:
- Не выдумывай того, чего нет в переписке. Если данных нет, пиши «не указано».
- Сохраняй конкретику: цифры, сроки, бюджет, ссылки, названия, пожелания.
- Отдельно отметь недоговорённости и вопросы, которые нужно уточнить клиенту.
- Формат — простой текст с заголовками, без Markdown и без HTML.

Структура:
1. Цель и задача
2. Что нужно сделать
3. Требования и пожелания клиента
4. Материалы и референсы
5. Сроки и бюджет
6. Что уточнить
7. Краткое резюме для исполнителя
"""


async def build_spec(chat: dict, messages: list[dict]) -> str:
    """Возвращает готовый текст ТЗ. При ошибке бросает RuntimeError."""
    if not config.GEMINI_API_KEY:
        raise RuntimeError("Ключ GEMINI_API_KEY не задан в настройках бота")

    lines = [
        f"Услуга: {config.service_title(chat['service_key'])}",
        f"Чат №{chat['id']}",
        "",
    ]
    for item in messages:
        who = "Клиент" if item["direction"] == "client_to_op" else "Специалист"
        lines.append(f"{who}: {item['body']}")

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": SYSTEM_PROMPT
                        + "\n\n=== ПЕРЕПИСКА ===\n"
                        + "\n".join(lines)
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 3000,
        },
    }

    url = URL_TEMPLATE.format(model=config.GEMINI_MODEL)
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url, params={"key": config.GEMINI_API_KEY}, json=payload
            ) as response:
                status = response.status
                try:
                    data = await response.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError):
                    data = {}
    except aiohttp.ClientError as exc:
        raise RuntimeError(f"Ошибка соединения с Gemini: {exc}")

    if status != 200:
        error = data.get("error") or {}
        message = error.get("message") or f"HTTP {status}"
        if status == 429:
            message = "лимит бесплатного Gemini исчерпан, попробуй позже"
        raise RuntimeError(message)

    candidates = data.get("candidates") or []
    if not candidates:
        error = data.get("error") or {}
        raise RuntimeError(error.get("message") or "Gemini вернул пустой ответ")

    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise RuntimeError("Gemini вернул пустой текст ТЗ")
    return text
