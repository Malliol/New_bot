"""
Загрузка конфигурации:
  - .env         — секреты и неизменяемые параметры (API-ключи, токены)
  - config.json  — рабочие настройки (каналы, ключевые слова); редактируется
                   через Telegram-команды администратора
"""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SETTINGS_FILE = Path("config.json")


# ── Секреты из .env ───────────────────────────────────────────────────────────

def _require(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise EnvironmentError(f"Обязательная переменная окружения не задана: {key}")
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


@dataclass
class EnvConfig:
    """Неизменяемые параметры из .env."""
    tg_api_id: int
    tg_api_hash: str
    tg_session_name: str
    admin_tg_id: int        # Telegram user ID администратора
    vk_token: str
    vk_peer_id: int
    log_file: str
    log_level: str


def load_env_config() -> EnvConfig:
    """Загрузить и провалидировать .env."""
    try:
        api_id = int(_require("TG_API_ID"))
    except ValueError:
        raise EnvironmentError("TG_API_ID должен быть числом")

    try:
        peer_id = int(_require("VK_PEER_ID"))
    except ValueError:
        raise EnvironmentError("VK_PEER_ID должен быть числом")

    try:
        admin_id = int(_require("ADMIN_TG_ID"))
    except ValueError:
        raise EnvironmentError("ADMIN_TG_ID должен быть числом (Telegram user ID)")

    return EnvConfig(
        tg_api_id=api_id,
        tg_api_hash=_require("TG_API_HASH"),
        tg_session_name=_optional("TG_SESSION_NAME", "news_relay_session"),
        admin_tg_id=admin_id,
        vk_token=_require("VK_TOKEN"),
        vk_peer_id=peer_id,
        log_file=_optional("LOG_FILE", "news_relay.log"),
        log_level=_optional("LOG_LEVEL", "INFO").upper(),
    )


# ── Рабочие настройки в config.json ──────────────────────────────────────────

@dataclass
class Settings:
    """
    Редактируемые настройки бота.
    Хранятся в config.json, изменяются через Telegram-команды.
    """
    channels: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)


def load_settings() -> Settings:
    """Прочитать config.json. Если файла нет — вернуть пустые настройки."""
    if not SETTINGS_FILE.exists():
        return Settings()
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return Settings(
            channels=data.get("channels", []),
            keywords=data.get("keywords", []),
        )
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Не удалось прочитать %s: %s", SETTINGS_FILE, e)
        return Settings()


def save_settings(settings: Settings) -> None:
    """Записать настройки в config.json."""
    try:
        SETTINGS_FILE.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.error("Не удалось сохранить %s: %s", SETTINGS_FILE, e)
