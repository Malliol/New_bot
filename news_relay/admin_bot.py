"""
Telegram-команды администратора через user-клиент Telethon.

Редактирование настроек перенесено в Mini App (Cloudflare Worker).
Здесь остаётся только /status — быстрый просмотр текущего config.json.
"""

import logging

from telethon import TelegramClient, events

from config import EnvConfig, load_settings

logger = logging.getLogger(__name__)


def register_admin_handlers(client: TelegramClient, cfg: EnvConfig) -> None:

    def _is_admin_pm(event: events.NewMessage.Event) -> bool:
        return (
            event.is_private
            and event.sender_id == cfg.admin_tg_id
            and (event.text or "").startswith("/")
        )

    @client.on(events.NewMessage(func=_is_admin_pm, pattern=r"^/status\b"))
    async def cmd_status(event: events.NewMessage.Event) -> None:
        s = load_settings()
        channels_str = "\n".join(f"  • {c}" for c in s.channels) or "  _(нет)_"
        keywords_str = "\n".join(f"  • {k}" for k in s.keywords) or "  _(нет — пересылаем всё)_"
        await event.respond(
            f"📊 **Текущие настройки** (из config.json)\n\n"
            f"**Каналы ({len(s.channels)}):**\n{channels_str}\n\n"
            f"**Ключевые слова ({len(s.keywords)}):**\n{keywords_str}\n\n"
            f"Для редактирования откройте Mini App через `/admin` в боте.",
            parse_mode="md",
        )
