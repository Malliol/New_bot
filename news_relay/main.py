"""
Точка входа.

Запускает компоненты в зависимости от наличия переменных в .env:
  - Всегда:    Telethon user-клиент (слушает каналы + текстовые команды)
  - Если BOT_TOKEN + WEBAPP_URL:   Bot polling (кнопка /admin → Mini App)
  - Если CF_*:                     KV sync (настройки из Cloudflare KV)
"""

import asyncio
import logging
import signal
import sys

from admin_bot import register_admin_handlers
from config import load_env_config, load_settings
from storage import get_connection, init_db
from tg_listener import build_client, register_handlers


def setup_logging(log_file: str, log_level: str) -> None:
    level = getattr(logging, log_level, logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, handlers=handlers)


async def run() -> None:
    try:
        cfg = load_env_config()
    except EnvironmentError as e:
        print(f"[ОШИБКА] Конфигурация: {e}")
        sys.exit(1)

    setup_logging(cfg.log_file, cfg.log_level)
    logger = logging.getLogger(__name__)

    settings = load_settings()
    if not settings.channels:
        logger.warning("Каналов нет. Добавьте через Telegram: /addchannel @username")

    logger.info("Запуск news-relay | admin_id=%d", cfg.admin_tg_id)

    if cfg.webapp_enabled:
        logger.info("Mini App: %s", cfg.webapp_url)
    else:
        logger.info("Mini App не настроен — управление через текстовые команды в Telegram")

    if cfg.cf_enabled:
        logger.info("Cloudflare KV sync: включён")
    else:
        logger.info("Cloudflare KV: не настроен — используется локальный config.json")

    db = get_connection()
    init_db(db)

    client = build_client(cfg)
    register_handlers(client, cfg, db)
    register_admin_handlers(client, cfg)

    # Собираем только нужные задачи
    tasks = []

    if cfg.webapp_enabled:
        from bot_runner import run_bot_polling
        tasks.append(run_bot_polling(cfg.bot_token, cfg.admin_tg_id, cfg.webapp_url))

    if cfg.cf_enabled:
        from kv_sync import run_kv_sync
        tasks.append(run_kv_sync(cfg.cf_account_id, cfg.cf_kv_namespace_id, cfg.cf_api_token))

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown(sig_name: str) -> None:
        logger.info("Сигнал %s — завершаем...", sig_name)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown, sig.name)
        except NotImplementedError:
            pass

    await client.start()
    logger.info("Telethon подключён. Жду сообщений.")

    await asyncio.gather(
        client.run_until_disconnected(),
        _wait_stop(stop_event, client, db),
        *tasks,
        return_exceptions=True,
    )


async def _wait_stop(stop_event, client, db) -> None:
    await stop_event.wait()
    logging.getLogger(__name__).info("Закрываем соединения...")
    await client.disconnect()
    db.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
