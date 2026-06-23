"""
Точка входа: запуск Telegram → VK news-relay бота.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

from config import load_config
from storage import get_connection, init_db
from tg_listener import build_client, register_handlers


def setup_logging(log_file: str, log_level: str) -> None:
    """Настроить логирование: в файл и в stdout одновременно."""
    level = getattr(logging, log_level, logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]

    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, handlers=handlers)


async def run() -> None:
    """Основная асинхронная точка входа."""
    # Загружаем конфиг
    try:
        cfg = load_config()
    except EnvironmentError as e:
        print(f"[ОШИБКА] Конфигурация: {e}")
        sys.exit(1)

    setup_logging(cfg.log_file, cfg.log_level)
    logger = logging.getLogger(__name__)

    logger.info("Запуск news-relay бота")
    logger.info("Каналы: %s", ", ".join(cfg.tg_channels))
    logger.info("VK peer_id: %d", cfg.vk_peer_id)
    if cfg.keywords:
        logger.info("Ключевые слова: %s", ", ".join(cfg.keywords))
    else:
        logger.info("Фильтр по ключевым словам отключён (пересылаем всё)")

    # Инициализируем БД
    db = get_connection()
    init_db(db)

    # Создаём Telethon-клиент
    client = build_client(cfg)

    # Регистрируем обработчики новых сообщений
    register_handlers(client, cfg, db)

    # Graceful shutdown при Ctrl+C или SIGTERM
    loop = asyncio.get_running_loop()

    def _shutdown(sig_name: str) -> None:
        logger.info("Получен сигнал %s, завершение работы...", sig_name)
        loop.create_task(_stop(client, db))

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown, sig.name)
        except NotImplementedError:
            # Windows не поддерживает add_signal_handler для всех сигналов
            pass

    # Запускаем клиент (первый запуск потребует интерактивного ввода номера/кода)
    await client.start()
    logger.info("Telethon подключён. Ожидание новых сообщений...")

    await client.run_until_disconnected()


async def _stop(client, db) -> None:
    """Корректно закрыть клиент и БД."""
    logging.getLogger(__name__).info("Закрываем соединения...")
    await client.disconnect()
    db.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
