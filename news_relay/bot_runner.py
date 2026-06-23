"""
Telegram Bot API polling.

Запускает отдельный бот (BotFather-токен), который при команде /admin
отправляет инлайн-кнопку, открывающую Mini App.

Использует только requests + asyncio.to_thread — без лишних зависимостей.
"""

import asyncio
import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

TG_API = "https://api.telegram.org/bot{token}/{method}"


def _call(token: str, method: str, **params) -> Any:
    """Синхронный вызов Telegram Bot API."""
    url = TG_API.format(token=token, method=method)
    resp = requests.post(url, json=params, timeout=15)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Bot API {method} ошибка: {data.get('description')}")
    return data.get("result")


def _send_admin_button(token: str, chat_id: int, webapp_url: str) -> None:
    """Отправить сообщение с кнопкой открытия Mini App."""
    _call(
        token, "sendMessage",
        chat_id=chat_id,
        text="🎛 *Панель управления News Relay*\n\nНажмите кнопку ниже, чтобы открыть админку.",
        parse_mode="Markdown",
        reply_markup={
            "inline_keyboard": [[
                {"text": "⚙️ Открыть админку", "web_app": {"url": webapp_url}},
            ]]
        },
    )


def _process_update(update: dict, token: str, admin_id: int, webapp_url: str) -> None:
    """Обработать одно обновление от Telegram."""
    msg = update.get("message")
    if not msg:
        return

    sender_id: int = msg.get("from", {}).get("id", 0)
    text: str = (msg.get("text") or "").strip()
    chat_id: int = msg.get("chat", {}).get("id", 0)

    # Реагируем только на команды от администратора
    if sender_id != admin_id:
        return

    if text.startswith("/admin") or text.startswith("/start"):
        try:
            _send_admin_button(token, chat_id, webapp_url)
            logger.info("Отправлена кнопка Mini App (chat_id=%d)", chat_id)
        except RuntimeError as e:
            logger.error("Ошибка отправки кнопки: %s", e)


async def run_bot_polling(token: str, admin_id: int, webapp_url: str) -> None:
    """
    Асинхронный long-polling бот.
    Вызывается как отдельная asyncio-задача рядом с Telethon-клиентом.
    """
    logger.info("Bot polling запущен (admin_id=%d)", admin_id)
    offset = 0
    consecutive_errors = 0

    while True:
        try:
            updates = await asyncio.to_thread(
                _call, token, "getUpdates",
                offset=offset,
                timeout=30,
                allowed_updates=["message"],
            )
            consecutive_errors = 0

            for upd in updates:
                offset = upd["update_id"] + 1
                try:
                    _process_update(upd, token, admin_id, webapp_url)
                except Exception as e:
                    logger.error("Ошибка обработки update %d: %s", upd.get("update_id"), e)

        except asyncio.CancelledError:
            logger.info("Bot polling остановлен")
            return
        except Exception as e:
            consecutive_errors += 1
            wait = min(2 ** consecutive_errors, 60)
            logger.error("Bot polling ошибка (попытка %d): %s. Повтор через %ds", consecutive_errors, e, wait)
            await asyncio.sleep(wait)
