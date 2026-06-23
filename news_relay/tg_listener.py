"""
Подписка на все входящие сообщения из каналов.
Список каналов и ключевые слова читаются из config.json при каждом
сообщении — изменения через админку применяются без перезапуска.
"""

import logging
import sqlite3

from telethon import TelegramClient, events

from config import EnvConfig, load_settings
from filters import passes_filter
from storage import is_already_sent, mark_as_sent
from vk_sender import VKSendError, format_post, send_message

logger = logging.getLogger(__name__)


def _normalize(handle: str) -> str:
    """Привести handle к виду @username для сравнения."""
    h = handle.lower().strip()
    if h.startswith("https://t.me/"):
        h = "@" + h.removeprefix("https://t.me/")
    if not h.startswith("@"):
        h = "@" + h
    return h


def _post_url(username: str, message_id: int) -> str:
    return f"https://t.me/{username.lstrip('@')}/{message_id}"


def build_client(cfg: EnvConfig) -> TelegramClient:
    proxy = None
    if cfg.proxy_host and cfg.proxy_port:
        import socks
        proxy_type = {
            "SOCKS5": socks.SOCKS5,
            "SOCKS4": socks.SOCKS4,
            "HTTP":   socks.HTTP,
        }.get(cfg.proxy_type.upper(), socks.SOCKS5)
        proxy = (proxy_type, cfg.proxy_host, cfg.proxy_port,
                 True, cfg.proxy_user, cfg.proxy_pass)
        logger.info("Используется прокси: %s %s:%d", cfg.proxy_type, cfg.proxy_host, cfg.proxy_port)

    return TelegramClient(cfg.tg_session_name, cfg.tg_api_id, cfg.tg_api_hash, proxy=proxy)


def register_handlers(client: TelegramClient, cfg: EnvConfig, db: sqlite3.Connection) -> None:
    """Зарегистрировать обработчик новых сообщений из каналов."""

    @client.on(events.NewMessage)
    async def handle_new_message(event: events.NewMessage.Event) -> None:
        if not event.is_channel:
            return

        message = event.message
        text: str = message.text or ""

        chat = await event.get_chat()
        channel_id = str(chat.id)

        if hasattr(chat, "username") and chat.username:
            channel_handle = _normalize(chat.username)
            channel_display = f"@{chat.username}"
            channel_username = chat.username
        else:
            channel_handle = f"@{channel_id}"
            channel_display = getattr(chat, "title", channel_id)
            channel_username = channel_display

        # Читаем актуальные настройки из config.json
        settings = load_settings()

        # Проверяем, входит ли канал в список отслеживаемых
        watched = [_normalize(h) for h in settings.channels]
        if channel_handle not in watched:
            return

        if not text.strip():
            return

        # Фильтрация по ключевым словам
        if not passes_filter(text, settings.keywords):
            logger.debug(
                "Пропуск: ключевые слова не найдены (msg_id=%d, channel=%s)",
                message.id, channel_display,
            )
            return

        # Дедупликация
        if is_already_sent(db, channel_id, message.id):
            return

        # Отправка в VK
        vk_text = format_post(channel_display, text, _post_url(channel_username, message.id))
        try:
            send_message(cfg.vk_token, cfg.vk_peer_id, vk_text)
            mark_as_sent(db, channel_id, message.id)
            logger.info("Отправлено в VK: %s msg_id=%d", channel_display, message.id)
        except VKSendError as e:
            logger.error("Ошибка VK (канал=%s, msg=%d): %s", channel_display, message.id, e)
