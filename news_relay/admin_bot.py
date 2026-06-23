"""
Telegram-команды администратора через user-клиент Telethon.

Работает в личке: бот отвечает на команды от ADMIN_TG_ID.
Используется как fallback когда Mini App (Cloudflare) недоступен.

Команды:
  /status                  — текущие настройки
  /channels                — список каналов
  /addchannel @name        — добавить канал
  /removechannel @name     — удалить канал
  /keywords                — список ключевых слов
  /addkeyword слово        — добавить слово
  /removekeyword слово     — удалить слово
  /clearkeywords           — удалить все слова (слать всё)
"""

import logging

from telethon import TelegramClient, events

from config import EnvConfig, load_settings, save_settings

logger = logging.getLogger(__name__)


def _normalize_channel(raw: str) -> str:
    h = raw.strip().lower()
    if h.startswith("https://t.me/"):
        h = "@" + h.removeprefix("https://t.me/")
    if not h.startswith("@"):
        h = "@" + h
    return h


def register_admin_handlers(client: TelegramClient, cfg: EnvConfig) -> None:

    def _is_admin(event: events.NewMessage.Event) -> bool:
        return (
            event.is_private
            and event.sender_id == cfg.admin_tg_id
            and (event.text or "").startswith("/")
        )

    async def _reply(event, text: str) -> None:
        await event.respond(text, parse_mode="md")

    # ── /status ───────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(func=_is_admin, pattern=r"^/status\b"))
    async def cmd_status(event):
        s = load_settings()
        ch = "\n".join(f"  • `{c}`" for c in s.channels) or "  _(нет)_"
        kw = "\n".join(f"  • `{k}`" for k in s.keywords) or "  _(нет — пересылаем всё)_"
        mode = "Mini App (Cloudflare)" if cfg.webapp_enabled else "текстовые команды"
        await _reply(event,
            f"📊 **Настройки**\n\n"
            f"**Каналы ({len(s.channels)}):**\n{ch}\n\n"
            f"**Ключевые слова ({len(s.keywords)}):**\n{kw}\n\n"
            f"**Режим управления:** {mode}\n"
            f"**VK peer\\_id:** `{cfg.vk_peer_id}`"
        )

    # ── /channels ─────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(func=_is_admin, pattern=r"^/channels\b"))
    async def cmd_channels(event):
        s = load_settings()
        if not s.channels:
            await _reply(event, "📋 Каналов нет.\n\nДобавить: `/addchannel @username`")
            return
        lines = "\n".join(f"{i+1}. `{c}`" for i, c in enumerate(s.channels))
        await _reply(event, f"📋 **Каналы ({len(s.channels)}):**\n\n{lines}")

    @client.on(events.NewMessage(func=_is_admin, pattern=r"^/addchannel\b"))
    async def cmd_add_channel(event):
        parts = (event.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await _reply(event, "⚠️ Использование: `/addchannel @username`")
            return
        handle = _normalize_channel(parts[1])
        s = load_settings()
        if handle in [_normalize_channel(c) for c in s.channels]:
            await _reply(event, f"ℹ️ `{handle}` уже в списке.")
            return
        s.channels.append(handle)
        save_settings(s)
        logger.info("Добавлен канал: %s", handle)
        await _reply(event, f"✅ Канал `{handle}` добавлен.")

    @client.on(events.NewMessage(func=_is_admin, pattern=r"^/removechannel\b"))
    async def cmd_remove_channel(event):
        parts = (event.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await _reply(event, "⚠️ Использование: `/removechannel @username`")
            return
        handle = _normalize_channel(parts[1])
        s = load_settings()
        before = len(s.channels)
        s.channels = [c for c in s.channels if _normalize_channel(c) != handle]
        if len(s.channels) == before:
            await _reply(event, f"❌ `{handle}` не найден.")
            return
        save_settings(s)
        logger.info("Удалён канал: %s", handle)
        await _reply(event, f"🗑 Канал `{handle}` удалён.")

    # ── /keywords ─────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(func=_is_admin, pattern=r"^/keywords\b"))
    async def cmd_keywords(event):
        s = load_settings()
        if not s.keywords:
            await _reply(event,
                "📋 Ключевых слов нет — бот пересылает **всё**.\n\n"
                "Добавить: `/addkeyword слово`"
            )
            return
        lines = "\n".join(f"{i+1}. `{k}`" for i, k in enumerate(s.keywords))
        await _reply(event, f"📋 **Ключевые слова ({len(s.keywords)}):**\n\n{lines}")

    @client.on(events.NewMessage(func=_is_admin, pattern=r"^/addkeyword\b"))
    async def cmd_add_keyword(event):
        parts = (event.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await _reply(event, "⚠️ Использование: `/addkeyword слово`")
            return
        word = parts[1].strip().lower()
        s = load_settings()
        if word in s.keywords:
            await _reply(event, f"ℹ️ `{word}` уже в списке.")
            return
        s.keywords.append(word)
        save_settings(s)
        logger.info("Добавлено ключевое слово: %s", word)
        await _reply(event, f"✅ Слово `{word}` добавлено.")

    @client.on(events.NewMessage(func=_is_admin, pattern=r"^/removekeyword\b"))
    async def cmd_remove_keyword(event):
        parts = (event.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await _reply(event, "⚠️ Использование: `/removekeyword слово`")
            return
        word = parts[1].strip().lower()
        s = load_settings()
        if word not in s.keywords:
            await _reply(event, f"❌ `{word}` не найден.")
            return
        s.keywords.remove(word)
        save_settings(s)
        logger.info("Удалено ключевое слово: %s", word)
        await _reply(event, f"🗑 Слово `{word}` удалено.")

    @client.on(events.NewMessage(func=_is_admin, pattern=r"^/clearkeywords\b"))
    async def cmd_clear_keywords(event):
        s = load_settings()
        count = len(s.keywords)
        if not count:
            await _reply(event, "ℹ️ Список ключевых слов уже пуст.")
            return
        s.keywords = []
        save_settings(s)
        logger.info("Очищены все ключевые слова (%d шт.)", count)
        await _reply(event,
            f"🗑 Удалено {count} слов. Теперь бот пересылает **всё** из отслеживаемых каналов."
        )
