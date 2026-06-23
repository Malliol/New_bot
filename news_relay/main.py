"""
Точка входа: запускает три компонента параллельно в одном event loop:
  1. Telethon user-клиент — слушает каналы + принимает команды в личке
  2. FastAPI + uvicorn    — отдаёт Mini App и REST API
  3. Bot polling          — BotFather-бот с кнопкой /admin → Mini App
"""

import asyncio
import logging
import signal
import sys

import uvicorn

from admin_bot import register_admin_handlers
from bot_runner import run_bot_polling
from config import load_env_config, load_settings
from storage import get_connection, init_db
from tg_listener import build_client, register_handlers
from webapp.app import app as fastapi_app, set_config as webapp_set_config


def setup_logging(log_file: str, log_level: str) -> None:
    level = getattr(logging, log_level, logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, handlers=handlers)
    # Приглушаем шум от uvicorn
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


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
        logger.warning("Список каналов пуст. Добавьте через бот: /admin → Каналы")

    logger.info("Запуск news-relay (admin_id=%d, webapp=%s)", cfg.admin_tg_id, cfg.webapp_url)

    # SQLite — только дедупликация
    db = get_connection()
    init_db(db)

    # Передаём конфиг в FastAPI-приложение
    webapp_set_config(cfg)

    # Telethon user-клиент
    client = build_client(cfg)
    register_handlers(client, cfg, db)
    register_admin_handlers(client, cfg)

    # uvicorn в том же event loop (без отдельного потока)
    uv_config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=cfg.webapp_port,
        loop="none",       # используем текущий loop
        log_level="warning",
    )
    uv_server = uvicorn.Server(uv_config)

    # Graceful shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown(sig_name: str) -> None:
        logger.info("Получен сигнал %s, завершение работы...", sig_name)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown, sig.name)
        except NotImplementedError:
            pass

    await client.start()
    logger.info(
        "Готово. Напишите /admin своему боту (@%s) чтобы открыть панель.",
        (await client.get_me()).username or "бот",
    )

    # Запускаем все три задачи параллельно
    tasks = await asyncio.gather(
        client.run_until_disconnected(),
        uv_server.serve(),
        run_bot_polling(cfg.bot_token, cfg.admin_tg_id, cfg.webapp_url),
        _wait_for_stop(stop_event, client, uv_server, db),
        return_exceptions=True,
    )

    for t in tasks:
        if isinstance(t, Exception) and not isinstance(t, asyncio.CancelledError):
            logger.error("Задача завершилась с ошибкой: %s", t)


async def _wait_for_stop(stop_event, client, uv_server, db) -> None:
    """Ждёт сигнала и корректно завершает все компоненты."""
    await stop_event.wait()
    logging.getLogger(__name__).info("Закрываем соединения...")
    uv_server.should_exit = True
    await client.disconnect()
    db.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
