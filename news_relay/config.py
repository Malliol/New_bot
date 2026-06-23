"""
Загрузка и валидация конфигурации из .env файла.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    """Получить обязательную переменную окружения или упасть с понятной ошибкой."""
    value = os.getenv(key, "").strip()
    if not value:
        raise EnvironmentError(f"Обязательная переменная окружения не задана: {key}")
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


@dataclass
class Config:
    # Telegram
    tg_api_id: int
    tg_api_hash: str
    tg_session_name: str
    tg_channels: List[str]          # список каналов (@username или ссылка)

    # VK
    vk_token: str
    vk_peer_id: int                 # peer_id беседы (2000000000 + chat_id)

    # Фильтрация
    keywords: List[str]             # пустой список = пересылать всё

    # Логирование
    log_file: str = "news_relay.log"
    log_level: str = "INFO"


def load_config() -> Config:
    """Загрузить конфигурацию, проверить обязательные поля."""

    # Парсим список каналов
    raw_channels = _require("TG_CHANNELS")
    channels = [ch.strip() for ch in raw_channels.split(",") if ch.strip()]
    if not channels:
        raise EnvironmentError("TG_CHANNELS не содержит ни одного канала")

    # Парсим ключевые слова (необязательное поле)
    raw_keywords = _optional("KEYWORDS", "")
    keywords = [kw.strip().lower() for kw in raw_keywords.split(",") if kw.strip()]

    try:
        api_id = int(_require("TG_API_ID"))
    except ValueError:
        raise EnvironmentError("TG_API_ID должен быть числом")

    try:
        peer_id = int(_require("VK_PEER_ID"))
    except ValueError:
        raise EnvironmentError("VK_PEER_ID должен быть числом")

    return Config(
        tg_api_id=api_id,
        tg_api_hash=_require("TG_API_HASH"),
        tg_session_name=_optional("TG_SESSION_NAME", "news_relay_session"),
        tg_channels=channels,
        vk_token=_require("VK_TOKEN"),
        vk_peer_id=peer_id,
        keywords=keywords,
        log_file=_optional("LOG_FILE", "news_relay.log"),
        log_level=_optional("LOG_LEVEL", "INFO").upper(),
    )
