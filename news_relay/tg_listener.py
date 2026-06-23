"""
Подписка на Telegram-каналы и обработка новых сообщений через Telethon.
"""

import logging
import sqlite3
from typing import List

from telethon import TelegramClient, events
from telethon.tl.types import Channel, PeerChannel

from config import Config
from filters import passes_filter
from storage import is_already_sent, mark_as_sent
from vk_sender import VKSendError, format_post, send_message

logger = logging.getLogger(__name__)


def _get_post_url(channel_username: str, message_id: int) -> str:
    """Сформировать прямую ссылку на пост в Telegram."""
    # Убираем @ если есть
    username = channel_username.lstrip("@")
    return f"https://t.me/{username}/{message_id}"


def build_client(cfg: Config) -> TelegramClient:
    """Создать Telethon-клиент с параметрами из конфига."""
    return TelegramClient(cfg.tg_session_name, cfg.tg_api_id, cfg.tg_api_hash)


def register_handlers(client: TelegramClient, cfg: Config, db: sqlite3.Connection) -> None:
    """
    Зарегистрировать обработчики новых сообщений для всех каналов из конфига.
    """

    @client.on(events.NewMessage(chats=cfg.tg_channels))
    async def handle_new_message(event: events.NewMessage.Event) -> None:
        message = event.message
        text: str = message.text or ""

        # Получаем идентификатор и имя канала
        chat = await event.get_chat()
        channel_id = str(chat.id)

        # Имя для отображения: username или title
        if hasattr(chat, "username") and chat.username:
            channel_display = f"@{chat.username}"
            channel_username = chat.username
        else:
            channel_display = getattr(chat, "title", channel_id)
            channel_username = channel_display

        message_id: int = message.id

        logger.debug(
            "Новое сообщение из %s (msg_id=%d, длина=%d символов)",
            channel_display, message_id, len(text),
        )

        # Пропускаем сообщения без текста (фото без подписи и т.п.)
        if not text.strip():
            logger.debug("Пропуск: сообщение без текста (msg_id=%d)", message_id)
            return

        # Фильтрация по ключевым словам
        if not passes_filter(text, cfg.keywords):
            logger.debug(
                "Пропуск: ключевые слова не найдены (msg_id=%d, channel=%s)",
                message_id, channel_display,
            )
            return

        # Дедупликация
        if is_already_sent(db, channel_id, message_id):
            logger.debug(
                "Пропуск: дубликат (msg_id=%d, channel=%s)", message_id, channel_display
            )
            return

        # Формируем и отправляем сообщение в VK
        post_url = _get_post_url(channel_username, message_id)
        vk_text = format_post(channel_display, text, post_url)

        try:
            send_message(cfg.vk_token, cfg.vk_peer_id, vk_text)
            mark_as_sent(db, channel_id, message_id)
            logger.info(
                "Отправлено в VK: канал=%s, msg_id=%d", channel_display, message_id
            )
        except VKSendError as e:
            # Логируем ошибку, но не падаем — следующие сообщения продолжат обрабатываться
            logger.error(
                "Ошибка отправки в VK (канал=%s, msg_id=%d): %s",
                channel_display, message_id, e,
            )
