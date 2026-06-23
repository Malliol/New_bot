"""
Точка входа VPS-компонента.
Запускает три задачи параллельно:
  1. Telethon user-клиент — слушает каналы + /status в личке
  2. Bot polling          — BotFather-бот с кнопкой /admin → Mini App
  3. KV sync              — каждые 30 сек тянет настройки из Cloudflare KV
"""

import asyncio
import logging
import signal
import sys

from admin_bot import register_admin_handlers
from bot_runner import run_bot_polling
from config import load_env_config, load_settings
from kv_sync import run_kv_sync
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
        logger.warning(
            "Каналы не найдены в config.json. "
            "Откройте Mini App (/admin в боте) и добавьте каналы. "
            "KV sync обновит config.json через %d сек.", 30
        )

    logger.info(
        "Запуск news-relay | admin=%d | webapp=%s",
        cfg.admin_tg_id, cfg.webapp_url,
    )

    db = get_connection()
    init_db(db)

    client = build_client(cfg)
    register_handlers(client, cfg, db)
    register_admin_handlers(client, cfg)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown(sig_name: str) -> None:
        logger.info("Сигнал %s — завершаем работу...", sig_name)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown, sig.name)
        except NotImplementedError:
            pass

    await client.start()
    logger.info("Telethon подключён. Напишите /admin боту чтобы открыть панель.")

    await asyncio.gather(
        client.run_until_disconnected(),
        run_bot_polling(cfg.bot_token, cfg.admin_tg_id, cfg.webapp_url),
        run_kv_sync(cfg.cf_account_id, cfg.cf_kv_namespace_id, cfg.cf_api_token),
        _wait_stop(stop_event, client, db),
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
