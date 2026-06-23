"""
Загрузка конфигурации:
  - .env         — секреты и неизменяемые параметры
  - config.json  — рабочие настройки (каналы, ключевые слова);
                   обновляется автоматически из Cloudflare KV через kv_sync.py
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
    admin_tg_id: int

    # BotFather-токен — для кнопки /admin → Mini App
    bot_token: str
    # Публичный URL воркера (https://news-relay-admin.workers.dev или свой домен)
    webapp_url: str

    # VK
    vk_token: str
    vk_peer_id: int

    # Cloudflare KV — для синхронизации настроек на VPS
    cf_account_id: str
    cf_kv_namespace_id: str
    cf_api_token: str

    # Логирование
    log_file: str
    log_level: str


def load_env_config() -> EnvConfig:
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
        raise EnvironmentError("ADMIN_TG_ID должен быть числом")

    return EnvConfig(
        tg_api_id=api_id,
        tg_api_hash=_require("TG_API_HASH"),
        tg_session_name=_optional("TG_SESSION_NAME", "news_relay_session"),
        admin_tg_id=admin_id,
        bot_token=_require("BOT_TOKEN"),
        webapp_url=_require("WEBAPP_URL").rstrip("/"),
        vk_token=_require("VK_TOKEN"),
        vk_peer_id=peer_id,
        cf_account_id=_require("CF_ACCOUNT_ID"),
        cf_kv_namespace_id=_require("CF_KV_NAMESPACE_ID"),
        cf_api_token=_require("CF_API_TOKEN"),
        log_file=_optional("LOG_FILE", "news_relay.log"),
        log_level=_optional("LOG_LEVEL", "INFO").upper(),
    )


# ── config.json (синхронизируется из KV) ─────────────────────────────────────

@dataclass
class Settings:
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
