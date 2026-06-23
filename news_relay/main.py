"""
Точка входа: запуск Telegram → VK news-relay бота.
"""

import asyncio
import logging
import signal
import sys

from admin_bot import register_admin_handlers
from config import load_env_config, load_settings, save_settings, Settings
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

    # Создаём config.json с пустыми настройками если файла нет
    settings = load_settings()
    if not settings.channels:
        logger.warning(
            "Список каналов пуст. Добавьте каналы через Telegram: /addchannel @username"
        )

    logger.info("Запуск news-relay бота (admin_id=%d)", cfg.admin_tg_id)

    db = get_connection()
    init_db(db)

    client = build_client(cfg)

    # Регистрируем оба обработчика на одном клиенте
    register_handlers(client, cfg, db)
    register_admin_handlers(client, cfg)

    loop = asyncio.get_running_loop()

    def _shutdown(sig_name: str) -> None:
        logger.info("Получен сигнал %s, завершение работы...", sig_name)
        loop.create_task(_stop(client, db))

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown, sig.name)
        except NotImplementedError:
            pass

    await client.start()
    logger.info("Telethon подключён. Жду сообщений.")
    logger.info(
        "Напишите /start себе (user_id=%d) через этот же аккаунт Telegram для управления.",
        cfg.admin_tg_id,
    )

    await client.run_until_disconnected()


async def _stop(client, db) -> None:
    logging.getLogger(__name__).info("Закрываем соединения...")
    await client.disconnect()
    db.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
