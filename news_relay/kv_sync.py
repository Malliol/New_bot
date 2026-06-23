"""
Синхронизация настроек из Cloudflare KV в локальный config.json.

Запускается как фоновая asyncio-задача рядом с Telethon-клиентом.
Каждые SYNC_INTERVAL секунд читает каналы и ключевые слова из KV
и обновляет config.json, если данные изменились.

Telethon-листенер читает config.json при каждом сообщении,
поэтому изменения через Mini App вступают в силу без перезапуска.
"""

import asyncio
import json
import logging

import requests

logger = logging.getLogger(__name__)

SYNC_INTERVAL = 30  # секунд между проверками KV
CF_API_BASE = "https://api.cloudflare.com/client/v4"


def _kv_url(account_id: str, namespace_id: str, key: str) -> str:
    return f"{CF_API_BASE}/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/{key}"


def _fetch_kv_value(account_id: str, namespace_id: str, api_token: str, key: str) -> list:
    """Прочитать одно значение из KV. Вернуть список или [] при ошибке/отсутствии."""
    url = _kv_url(account_id, namespace_id, key)
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=10,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return json.loads(resp.text)
    except (requests.RequestException, json.JSONDecodeError) as e:
        logger.warning("KV sync: не удалось прочитать '%s': %s", key, e)
        return None  # None = пропустить обновление, не затирать старое


def _sync_once(account_id: str, namespace_id: str, api_token: str, settings_path: str) -> bool:
    """
    Прочитать channels и keywords из KV, сравнить с config.json.
    Вернуть True, если файл был обновлён.
    """
    channels = _fetch_kv_value(account_id, namespace_id, api_token, "channels")
    keywords = _fetch_kv_value(account_id, namespace_id, api_token, "keywords")

    # Если хотя бы один ключ вернул ошибку — не трогаем файл
    if channels is None or keywords is None:
        return False

    new_data = {"channels": channels, "keywords": keywords}

    # Читаем текущий файл (если есть) — обновляем только при изменениях
    try:
        with open(settings_path, encoding="utf-8") as f:
            current = json.load(f)
        if current == new_data:
            return False
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

    logger.info(
        "KV sync: config.json обновлён (каналов=%d, слов=%d)",
        len(channels), len(keywords),
    )
    return True


async def run_kv_sync(account_id: str, namespace_id: str, api_token: str,
                      settings_path: str = "config.json") -> None:
    """Запустить бесконечный цикл синхронизации KV → config.json."""
    logger.info("KV sync запущен (интервал=%ds)", SYNC_INTERVAL)

    while True:
        try:
            await asyncio.to_thread(
                _sync_once, account_id, namespace_id, api_token, settings_path
            )
        except asyncio.CancelledError:
            logger.info("KV sync остановлен")
            return
        except Exception as e:
            logger.error("KV sync неожиданная ошибка: %s", e)

        await asyncio.sleep(SYNC_INTERVAL)
