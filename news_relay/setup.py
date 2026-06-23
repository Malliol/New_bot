#!/usr/bin/env python3
"""
Быстрое развёртывание News Relay на локальном ПК / VPS.

Запуск:
    python setup.py

Скрипт:
  1. Проверяет версию Python
  2. Создаёт виртуальное окружение .venv
  3. Устанавливает зависимости
  4. Интерактивно собирает .env (известные значения уже предзаполнены)
  5. Создаёт пустой config.json если его нет
  6. Запускает первичный логин Telethon (создание .session)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# ── Цвета для терминала ───────────────────────────────────────────────────────
G = "\033[92m"   # зелёный
Y = "\033[93m"   # жёлтый
R = "\033[91m"   # красный
B = "\033[94m"   # синий
RESET = "\033[0m"
BOLD  = "\033[1m"

def ok(msg):    print(f"{G}✓{RESET} {msg}")
def warn(msg):  print(f"{Y}⚠ {msg}{RESET}")
def err(msg):   print(f"{R}✗ {msg}{RESET}")
def info(msg):  print(f"{B}→{RESET} {msg}")
def header(msg):print(f"\n{BOLD}{msg}{RESET}")


# ── Проверка Python ───────────────────────────────────────────────────────────

def check_python():
    if sys.version_info < (3, 11):
        err(f"Требуется Python 3.11+, у вас {sys.version.split()[0]}")
        sys.exit(1)
    ok(f"Python {sys.version.split()[0]}")


# ── Виртуальное окружение ─────────────────────────────────────────────────────

def setup_venv(base: Path):
    venv = base / ".venv"
    if venv.exists():
        ok(".venv уже существует")
    else:
        info("Создаю .venv...")
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        ok(".venv создан")
    return venv


def pip_install(venv: Path, requirements: Path):
    pip = venv / ("Scripts/pip.exe" if os.name == "nt" else "bin/pip")
    info("Устанавливаю зависимости...")
    subprocess.run(
        [str(pip), "install", "-q", "-r", str(requirements)],
        check=True,
    )
    ok("Зависимости установлены")


# ── Интерактивный ввод ────────────────────────────────────────────────────────

def ask(prompt: str, default: str = "", secret: bool = False) -> str:
    """Запросить значение у пользователя. Если есть default — предложить его."""
    if default:
        display = ("*" * 8) if secret else default
        full_prompt = f"  {prompt} [{display}]: "
    else:
        full_prompt = f"  {prompt}: "

    while True:
        try:
            value = input(full_prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            sys.exit(0)

        if value:
            return value
        if default:
            return default
        warn("Значение не может быть пустым")


def ask_optional(prompt: str, default: str = "") -> str:
    """Запросить необязательное значение (Enter = пропустить)."""
    display = default if default else "пропустить"
    full_prompt = f"  {prompt} [{display}]: "
    try:
        value = input(full_prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(0)
    return value if value else default


# ── Сборка .env ───────────────────────────────────────────────────────────────

# Значения, известные заранее (заполнены при деплое)
PREFILLED = {
    "VK_TOKEN":     "vk1.a.oERBmebuNTlwb28eYGa8vd9ZSZX2SRv3uwGQOXcvArcTEpuAHHxUHKJb0a5b08RHO955cYOaYIXWTNNkzbFcCTqY5__StvWzOwuhAEf4Msx3Oe0j2KRNi4yl8ythMHYTl0gil0CGaluCqknWmNVhOeRdwKcT77AlORmnVo0dw3RaSPNQNkQJN76AUDdk8lCHGVzmCx2wq5FT-y79iQY6Iw",
    "BOT_TOKEN":    "2034521246:AAG2SrUcEj5pu2p8orF45ML4_d54kkGh7Bg",
    "ADMIN_TG_ID":  "1367102384",
}


def build_env(env_path: Path) -> None:
    header("📝 Настройка .env")

    # Читаем существующий .env если есть
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()
        warn(".env уже существует — предзаполним текущими значениями")

    def get(key: str) -> str:
        return existing.get(key, PREFILLED.get(key, ""))

    print()
    print("  Обязательные параметры Telegram (получить на https://my.telegram.org/apps):")
    tg_api_id   = ask("TG_API_ID (число)", get("TG_API_ID"))
    tg_api_hash = ask("TG_API_HASH", get("TG_API_HASH"), secret=True)

    print()
    print("  VKонтакте:")
    print("  VK_PEER_ID — peer_id беседы = 2000000000 + номер чата")
    print("  Пример: vk.com/im?sel=c42 → VK_PEER_ID=2000000042")
    vk_peer_id = ask("VK_PEER_ID", get("VK_PEER_ID"))

    print()
    print("  Опционально — Cloudflare (для Mini App; оставьте пустым для локального теста):")
    cf_account_id    = ask_optional("CF_ACCOUNT_ID",    get("CF_ACCOUNT_ID"))
    cf_kv_ns_id      = ask_optional("CF_KV_NAMESPACE_ID", get("CF_KV_NAMESPACE_ID"))
    cf_api_token     = ask_optional("CF_API_TOKEN",     get("CF_API_TOKEN"))
    webapp_url       = ask_optional("WEBAPP_URL (Worker URL)", get("WEBAPP_URL"))

    env_lines = f"""\
# ── Telegram MTProto ──────────────────────────────────────────────────────────
TG_API_ID={tg_api_id}
TG_API_HASH={tg_api_hash}
TG_SESSION_NAME=news_relay_session

# ── Администратор ─────────────────────────────────────────────────────────────
ADMIN_TG_ID={PREFILLED['ADMIN_TG_ID']}

# ── Telegram Bot ──────────────────────────────────────────────────────────────
BOT_TOKEN={PREFILLED['BOT_TOKEN']}
WEBAPP_URL={webapp_url}

# ── ВКонтакте ─────────────────────────────────────────────────────────────────
VK_TOKEN={PREFILLED['VK_TOKEN']}
VK_PEER_ID={vk_peer_id}

# ── Cloudflare KV (опционально) ───────────────────────────────────────────────
CF_ACCOUNT_ID={cf_account_id}
CF_KV_NAMESPACE_ID={cf_kv_ns_id}
CF_API_TOKEN={cf_api_token}

# ── Логирование ───────────────────────────────────────────────────────────────
LOG_FILE=news_relay.log
LOG_LEVEL=INFO
"""
    env_path.write_text(env_lines, encoding="utf-8")
    ok(".env создан")


# ── config.json ───────────────────────────────────────────────────────────────

def ensure_config_json(base: Path) -> None:
    cfg = base / "config.json"
    if cfg.exists():
        ok("config.json уже существует")
        return
    cfg.write_text(json.dumps({"channels": [], "keywords": []}, ensure_ascii=False, indent=2))
    ok("config.json создан (пустой — добавьте каналы через /addchannel)")


# ── Первый запуск Telethon ────────────────────────────────────────────────────

def first_login(venv: Path, base: Path) -> None:
    header("🔑 Авторизация Telegram")
    print("""
  Сейчас запустится Telethon для первичного входа.
  Вам нужно будет ввести:
    1. Номер телефона (с кодом страны, например +79001234567)
    2. Код из Telegram
    3. Пароль 2FA (если включён)

  После успешного входа создастся файл news_relay_session.session
  и бот начнёт работать. Остановить: Ctrl+C
""")
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        subprocess.run([str(python), "main.py"], cwd=str(base))
    except KeyboardInterrupt:
        pass


# ── Главный поток ─────────────────────────────────────────────────────────────

def main():
    base = Path(__file__).parent.resolve()

    print(f"""
{BOLD}╔══════════════════════════════════════════╗
║      News Relay — Быстрое развёртывание  ║
╚══════════════════════════════════════════╝{RESET}

  Папка проекта: {base}
""")

    check_python()

    header("📦 Виртуальное окружение")
    venv = setup_venv(base)
    pip_install(venv, base / "requirements.txt")

    header("⚙️  Конфигурация")
    build_env(base / ".env")
    ensure_config_json(base)

    print(f"""
{G}{BOLD}✓ Готово!{RESET}

Что дальше:
  • Добавьте каналы:     напишите /addchannel @channel боту (user-сессия)
  • Добавьте слова:      напишите /addkeyword слово боту
  • Проверьте статус:    напишите /status боту

{B}Команды для запуска:{RESET}
  cd {base}
  source .venv/bin/activate     # Linux/Mac
  .venv\\Scripts\\activate         # Windows
  python main.py
""")

    try:
        answer = input("  Запустить бота сейчас? [Y/n]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return

    if answer in ("", "y", "д", "да"):
        first_login(venv, base)


if __name__ == "__main__":
    main()
