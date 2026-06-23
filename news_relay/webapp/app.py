"""
FastAPI-сервер для Mini App.

Отдаёт index.html и предоставляет REST API для управления настройками.
Все изменяющие запросы валидируют Telegram initData — только ADMIN_TG_ID
имеет доступ.
"""

import hashlib
import hmac
import json
import urllib.parse
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# config.py находится на уровень выше — импортируем напрямую
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import EnvConfig, load_settings, save_settings

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="News Relay Admin", docs_url=None, redoc_url=None)

# Глобальный конфиг — устанавливается из main.py при старте
_cfg: EnvConfig | None = None


def set_config(cfg: EnvConfig) -> None:
    global _cfg
    _cfg = cfg


# ── Telegram initData валидация ───────────────────────────────────────────────

def _validate_init_data(init_data: str, bot_token: str) -> dict:
    """
    Проверить HMAC-подпись Telegram WebApp initData.
    Документация: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", "")
    if not received_hash:
        raise ValueError("hash отсутствует в initData")

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Неверная подпись initData")

    return parsed


def require_admin(x_init_data: str = Header(..., alias="X-Init-Data")) -> None:
    """Dependency: проверить initData и убедиться, что запрос от ADMIN_TG_ID."""
    if _cfg is None:
        raise HTTPException(503, "Сервер не инициализирован")
    try:
        parsed = _validate_init_data(x_init_data, _cfg.bot_token)
        user = json.loads(parsed.get("user", "{}"))
        if user.get("id") != _cfg.admin_tg_id:
            raise HTTPException(403, "Доступ запрещён")
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(401, f"Ошибка авторизации: {e}")


# ── Pydantic-схемы ────────────────────────────────────────────────────────────

class ChannelBody(BaseModel):
    handle: str   # @username или https://t.me/username


class KeywordBody(BaseModel):
    word: str


# ── HTML-страница ─────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


# ── API: статус ───────────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status(_=Depends(require_admin)):
    s = load_settings()
    return {"channels": s.channels, "keywords": s.keywords}


# ── API: каналы ───────────────────────────────────────────────────────────────

@app.get("/api/channels")
async def list_channels(_=Depends(require_admin)):
    return load_settings().channels


@app.post("/api/channels", status_code=201)
async def add_channel(body: ChannelBody, _=Depends(require_admin)):
    handle = _normalize_channel(body.handle)
    s = load_settings()
    normalized = [_normalize_channel(c) for c in s.channels]
    if handle in normalized:
        raise HTTPException(409, f"Канал {handle} уже существует")
    s.channels.append(handle)
    save_settings(s)
    return {"handle": handle}


@app.delete("/api/channels/{handle:path}")
async def remove_channel(handle: str, _=Depends(require_admin)):
    handle = _normalize_channel(handle)
    s = load_settings()
    before = len(s.channels)
    s.channels = [c for c in s.channels if _normalize_channel(c) != handle]
    if len(s.channels) == before:
        raise HTTPException(404, f"Канал {handle} не найден")
    save_settings(s)
    return {"deleted": handle}


# ── API: ключевые слова ───────────────────────────────────────────────────────

@app.get("/api/keywords")
async def list_keywords(_=Depends(require_admin)):
    return load_settings().keywords


@app.post("/api/keywords", status_code=201)
async def add_keyword(body: KeywordBody, _=Depends(require_admin)):
    word = body.word.strip().lower()
    if not word:
        raise HTTPException(400, "Слово не может быть пустым")
    s = load_settings()
    if word in s.keywords:
        raise HTTPException(409, f"Слово '{word}' уже существует")
    s.keywords.append(word)
    save_settings(s)
    return {"word": word}


@app.delete("/api/keywords/{word}")
async def remove_keyword(word: str, _=Depends(require_admin)):
    word = word.lower()
    s = load_settings()
    if word not in s.keywords:
        raise HTTPException(404, f"Слово '{word}' не найдено")
    s.keywords.remove(word)
    save_settings(s)
    return {"deleted": word}


@app.delete("/api/keywords")
async def clear_keywords(_=Depends(require_admin)):
    s = load_settings()
    count = len(s.keywords)
    s.keywords = []
    save_settings(s)
    return {"deleted": count}


# ── Утилиты ───────────────────────────────────────────────────────────────────

def _normalize_channel(handle: str) -> str:
    h = handle.strip().lower()
    if h.startswith("https://t.me/"):
        h = "@" + h.removeprefix("https://t.me/")
    if not h.startswith("@"):
        h = "@" + h
    return h
