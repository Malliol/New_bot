"""
Загрузка конфигурации:
  - .env         — секреты и параметры
  - config.json  — каналы и ключевые слова (редактируются через бота или Mini App)
"""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

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
    # Telegram MTProto (user-сессия для чтения каналов)
    tg_api_id: int
    tg_api_hash: str
    tg_session_name: str
    admin_tg_id: int

    # VK
    vk_token: str
    vk_peer_id: int

    # Telegram Bot (кнопка /admin → Mini App); опционально для локального запуска
    bot_token: Optional[str]
    webapp_url: Optional[str]

    # Cloudflare KV (синхронизация настроек); опционально — без них используется локальный config.json
    cf_account_id: Optional[str]
    cf_kv_namespace_id: Optional[str]
    cf_api_token: Optional[str]

    # Логирование
    log_file: str
    log_level: str

    @property
    def cf_enabled(self) -> bool:
        """True, если все CF-переменные заданы и KV-синхронизация активна."""
        return bool(self.cf_account_id and self.cf_kv_namespace_id and self.cf_api_token)

    @property
    def webapp_enabled(self) -> bool:
        """True, если задан bot_token и webapp_url (Mini App через CF Worker)."""
        return bool(self.bot_token and self.webapp_url)


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
        vk_token=_require("VK_TOKEN"),
        vk_peer_id=peer_id,
        bot_token=_optional("BOT_TOKEN") or None,
        webapp_url=(_optional("WEBAPP_URL") or None),
        cf_account_id=_optional("CF_ACCOUNT_ID") or None,
        cf_kv_namespace_id=_optional("CF_KV_NAMESPACE_ID") or None,
        cf_api_token=_optional("CF_API_TOKEN") or None,
        log_file=_optional("LOG_FILE", "news_relay.log"),
        log_level=_optional("LOG_LEVEL", "INFO").upper(),
    )


# ── config.json ───────────────────────────────────────────────────────────────

@dataclass
class Settings:
    channels: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)


def load_settings() -> Settings:
    if not SETTINGS_FILE.exists():
        return Settings()
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return Settings(channels=data.get("channels", []), keywords=data.get("keywords", []))
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Не удалось прочитать %s: %s", SETTINGS_FILE, e)
        return Settings()


def save_settings(settings: Settings) -> None:
    try:
        SETTINGS_FILE.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.error("Не удалось сохранить %s: %s", SETTINGS_FILE, e)
