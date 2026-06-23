"""
SQLite-хранилище для дедупликации отправленных постов.
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = "news_relay.db"


def get_connection() -> sqlite3.Connection:
    """Открыть соединение с БД (создаёт файл при первом запуске)."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Создать таблицы, если их нет."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_posts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id  TEXT    NOT NULL,
            message_id  INTEGER NOT NULL,
            sent_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(channel_id, message_id)
        )
    """)
    conn.commit()
    logger.info("База данных инициализирована: %s", DB_PATH)


def is_already_sent(conn: sqlite3.Connection, channel_id: str, message_id: int) -> bool:
    """Вернуть True, если пост уже был отправлен."""
    row = conn.execute(
        "SELECT 1 FROM sent_posts WHERE channel_id = ? AND message_id = ?",
        (channel_id, message_id),
    ).fetchone()
    return row is not None


def mark_as_sent(conn: sqlite3.Connection, channel_id: str, message_id: int) -> None:
    """Пометить пост как отправленный (игнорировать дубликат)."""
    try:
        conn.execute(
            "INSERT OR IGNORE INTO sent_posts (channel_id, message_id) VALUES (?, ?)",
            (channel_id, message_id),
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.error("Ошибка записи в БД (channel=%s, msg=%s): %s", channel_id, message_id, e)
