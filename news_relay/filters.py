"""
Фильтрация сообщений по ключевым словам.
"""

from typing import List


def passes_filter(text: str, keywords: List[str]) -> bool:
    """
    Вернуть True, если:
    - список keywords пустой (фильтрация отключена), ИЛИ
    - хотя бы одно ключевое слово найдено в тексте (без учёта регистра).
    """
    if not keywords:
        return True
    lower_text = text.lower()
    return any(kw in lower_text for kw in keywords)
