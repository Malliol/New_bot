"""
Telegram-администратор бота.

Работает через тот же user-клиент Telethon: слушает личные сообщения
от ADMIN_TG_ID и отвечает на команды управления ботом.

Доступные команды
─────────────────
/start   — приветствие и список команд
/status  — текущее состояние (каналы, ключевые слова, VK peer)

Каналы:
/channels              — показать список каналов
/addchannel @name      — добавить канал
/removechannel @name   — удалить канал

Ключевые слова:
/keywords              — показать список слов
/addkeyword слово      — добавить слово
/removekeyword слово   — удалить слово
/clearkeywords         — удалить все слова (пересылать всё)
"""

import logging
import sqlite3

from telethon import TelegramClient, events
from telethon.tl.custom import Message

from config import EnvConfig, Settings, load_settings, save_settings

logger = logging.getLogger(__name__)

HELP_TEXT = """\
🤖 **News Relay — панель управления**

**Статус**
/status — текущие каналы, слова, VK peer

**Каналы** (источники в Telegram)
/channels — показать список
/addchannel @channel\_name — добавить
/removechannel @channel\_name — удалить

**Ключевые слова** (триггеры пересылки)
/keywords — показать список
/addkeyword слово — добавить
/removekeyword слово — удалить
/clearkeywords — удалить все (пересылать всё подряд)
"""


def _normalize_channel(raw: str) -> str:
    """Привести введённый пользователем handle к @username."""
    h = raw.strip().lower()
    if h.startswith("https://t.me/"):
        h = "@" + h.removeprefix("https://t.me/")
    if not h.startswith("@"):
        h = "@" + h
    return h


def register_admin_handlers(client: TelegramClient, cfg: EnvConfig) -> None:
    """Зарегистрировать обработчики команд от администратора."""

    # Фильтр: только личные сообщения от admin_tg_id, начинающиеся с /
    def _is_admin_pm(event: events.NewMessage.Event) -> bool:
        return (
            event.is_private
            and event.sender_id == cfg.admin_tg_id
            and (event.text or "").startswith("/")
        )

    async def _reply(event: events.NewMessage.Event, text: str) -> None:
        await event.respond(text, parse_mode="md")

    # ── /start и /help ────────────────────────────────────────────────────────

    @client.on(events.NewMessage(func=_is_admin_pm, pattern=r"^/start\b"))
    async def cmd_start(event: events.NewMessage.Event) -> None:
        await _reply(event, HELP_TEXT)

    @client.on(events.NewMessage(func=_is_admin_pm, pattern=r"^/help\b"))
    async def cmd_help(event: events.NewMessage.Event) -> None:
        await _reply(event, HELP_TEXT)

    # ── /status ───────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(func=_is_admin_pm, pattern=r"^/status\b"))
    async def cmd_status(event: events.NewMessage.Event) -> None:
        s = load_settings()

        channels_str = (
            "\n".join(f"  • {c}" for c in s.channels) or "  _(нет)_"
        )
        keywords_str = (
            "\n".join(f"  • {k}" for k in s.keywords) or "  _(нет — пересылаем всё)_"
        )

        text = (
            f"📊 **Текущие настройки**\n\n"
            f"**Каналы ({len(s.channels)}):**\n{channels_str}\n\n"
            f"**Ключевые слова ({len(s.keywords)}):**\n{keywords_str}\n\n"
            f"**VK peer\_id:** `{cfg.vk_peer_id}`"
        )
        await _reply(event, text)

    # ── /channels ─────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(func=_is_admin_pm, pattern=r"^/channels\b"))
    async def cmd_channels(event: events.NewMessage.Event) -> None:
        s = load_settings()
        if not s.channels:
            await _reply(event, "📋 Список каналов пуст.\n\nДобавьте: `/addchannel @username`")
            return
        lines = "\n".join(f"{i+1}. `{c}`" for i, c in enumerate(s.channels))
        await _reply(event, f"📋 **Каналы ({len(s.channels)}):**\n\n{lines}")

    @client.on(events.NewMessage(func=_is_admin_pm, pattern=r"^/addchannel\b"))
    async def cmd_add_channel(event: events.NewMessage.Event) -> None:
        parts = (event.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await _reply(event, "⚠️ Использование: `/addchannel @username`")
            return

        handle = _normalize_channel(parts[1])
        s = load_settings()

        if handle in [_normalize_channel(c) for c in s.channels]:
            await _reply(event, f"ℹ️ Канал `{handle}` уже в списке.")
            return

        s.channels.append(handle)
        save_settings(s)
        logger.info("Админ добавил канал: %s", handle)
        await _reply(event, f"✅ Канал `{handle}` добавлен.")

    @client.on(events.NewMessage(func=_is_admin_pm, pattern=r"^/removechannel\b"))
    async def cmd_remove_channel(event: events.NewMessage.Event) -> None:
        parts = (event.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await _reply(event, "⚠️ Использование: `/removechannel @username`")
            return

        handle = _normalize_channel(parts[1])
        s = load_settings()

        normalized = [_normalize_channel(c) for c in s.channels]
        if handle not in normalized:
            await _reply(event, f"❌ Канал `{handle}` не найден в списке.")
            return

        s.channels = [c for c in s.channels if _normalize_channel(c) != handle]
        save_settings(s)
        logger.info("Админ удалил канал: %s", handle)
        await _reply(event, f"🗑 Канал `{handle}` удалён.")

    # ── /keywords ─────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(func=_is_admin_pm, pattern=r"^/keywords\b"))
    async def cmd_keywords(event: events.NewMessage.Event) -> None:
        s = load_settings()
        if not s.keywords:
            await _reply(
                event,
                "📋 Ключевые слова не заданы — бот пересылает **все** сообщения.\n\n"
                "Добавить: `/addkeyword слово`",
            )
            return
        lines = "\n".join(f"{i+1}. `{k}`" for i, k in enumerate(s.keywords))
        await _reply(event, f"📋 **Ключевые слова ({len(s.keywords)}):**\n\n{lines}")

    @client.on(events.NewMessage(func=_is_admin_pm, pattern=r"^/addkeyword\b"))
    async def cmd_add_keyword(event: events.NewMessage.Event) -> None:
        parts = (event.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await _reply(event, "⚠️ Использование: `/addkeyword слово`")
            return

        word = parts[1].strip().lower()
        s = load_settings()

        if word in s.keywords:
            await _reply(event, f"ℹ️ Слово `{word}` уже в списке.")
            return

        s.keywords.append(word)
        save_settings(s)
        logger.info("Админ добавил ключевое слово: %s", word)
        await _reply(event, f"✅ Слово `{word}` добавлено.")

    @client.on(events.NewMessage(func=_is_admin_pm, pattern=r"^/removekeyword\b"))
    async def cmd_remove_keyword(event: events.NewMessage.Event) -> None:
        parts = (event.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await _reply(event, "⚠️ Использование: `/removekeyword слово`")
            return

        word = parts[1].strip().lower()
        s = load_settings()

        if word not in s.keywords:
            await _reply(event, f"❌ Слово `{word}` не найдено.")
            return

        s.keywords.remove(word)
        save_settings(s)
        logger.info("Админ удалил ключевое слово: %s", word)
        await _reply(event, f"🗑 Слово `{word}` удалено.")

    @client.on(events.NewMessage(func=_is_admin_pm, pattern=r"^/clearkeywords\b"))
    async def cmd_clear_keywords(event: events.NewMessage.Event) -> None:
        s = load_settings()
        count = len(s.keywords)
        if count == 0:
            await _reply(event, "ℹ️ Список ключевых слов уже пуст.")
            return
        s.keywords = []
        save_settings(s)
        logger.info("Админ очистил все ключевые слова (%d шт.)", count)
        await _reply(
            event,
            f"🗑 Удалено {count} слов. Теперь бот пересылает **все** сообщения из отслеживаемых каналов.",
        )
