"""
Отправка сообщений в беседу ВКонтакте через API сообщества.
"""

import logging
import random
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

VK_API_VERSION = "5.199"
VK_API_BASE = "https://api.vk.com/method"

# Параметры повтора при ошибках сети/API
MAX_RETRIES = 4
BACKOFF_BASE = 2  # секунды: 2, 4, 8, 16

# Коды ошибок VK API, при которых повтор не имеет смысла
NON_RETRYABLE_VK_ERRORS = {
    5,   # неверный токен
    7,   # нет прав
    9,   # слишком много одинаковых запросов
    10,  # внутренняя ошибка сервера (иногда стоит не повторять)
}


class VKSendError(Exception):
    """Ошибка отправки сообщения в VK."""


def send_message(token: str, peer_id: int, text: str) -> None:
    """
    Отправить сообщение в беседу VK.
    При сетевых ошибках и ошибках сервера — повторять с экспоненциальным бэкофом.
    """
    params = {
        "access_token": token,
        "peer_id": peer_id,
        "message": text,
        "random_id": random.randint(0, 2**31 - 1),
        "v": VK_API_VERSION,
    }

    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                f"{VK_API_BASE}/messages.send",
                data=params,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                code = data["error"].get("error_code", -1)
                msg = data["error"].get("error_msg", "неизвестная ошибка")
                if code in NON_RETRYABLE_VK_ERRORS:
                    raise VKSendError(f"VK API ошибка {code}: {msg}")
                # Ошибки сервера — пробуем повторить
                raise VKSendError(f"VK API ошибка {code}: {msg}")

            logger.debug("Сообщение отправлено в VK, peer_id=%d", peer_id)
            return  # успех

        except (requests.RequestException, VKSendError) as e:
            last_error = e
            is_non_retryable = (
                isinstance(e, VKSendError)
                and any(str(code) in str(e) for code in NON_RETRYABLE_VK_ERRORS)
            )
            if is_non_retryable or attempt == MAX_RETRIES:
                break

            wait = BACKOFF_BASE ** attempt
            logger.warning(
                "Попытка %d/%d не удалась (%s). Повтор через %ds...",
                attempt, MAX_RETRIES, e, wait,
            )
            time.sleep(wait)

    raise VKSendError(f"Не удалось отправить сообщение после {MAX_RETRIES} попыток: {last_error}")


def format_post(channel_name: str, text: str, post_url: str) -> str:
    """Сформировать текст поста для VK."""
    parts = [f"📣 {channel_name}"]
    if text:
        parts.append(f"\n{text}")
    parts.append(f"\n🔗 {post_url}")
    return "\n".join(parts)
