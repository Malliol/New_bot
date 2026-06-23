# Telegram → VK News Relay

Бот читает заданные Telegram-каналы через Telethon (user-сессию)
и пересылает посты в беседу ВКонтакте через API сообщества.

---

## Архитектура

```
[Telegram-каналы]
    └─► Telethon (events.NewMessage)
           └─► filters.py  — фильтр по ключевым словам
                  └─► storage.py  — дедупликация (SQLite)
                         └─► vk_sender.py  — messages.send → [VK беседа]
```

---

## Требования

- Python 3.11+
- VPS / сервер с постоянным интернет-соединением

---

## Установка

### 1. Клонировать/скопировать проект

```bash
mkdir -p /opt/news_relay
cp -r news_relay/* /opt/news_relay/
cd /opt/news_relay
```

### 2. Создать виртуальное окружение и установить зависимости

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Заполнить .env

```bash
cp .env.example .env
nano .env   # заполнить все поля
```

#### Как получить Telegram API ID и Hash

1. Войти на https://my.telegram.org/apps
2. Создать приложение → скопировать `api_id` и `api_hash`

#### Как получить токен сообщества ВК

1. Перейти в сообщество → **Управление** → **Настройки** → **Работа с API**
2. Создать ключ доступа с правами **Сообщения**
3. Убедиться, что у сообщества включено **Разрешить отправку сообщений**

#### Как узнать VK_PEER_ID беседы

Откройте беседу ВКонтакте в браузере. В URL будет:
`vk.com/im?sel=c<number>` — это `chat_id`.

```
VK_PEER_ID = 2000000000 + chat_id
```

Например, `c42` → `VK_PEER_ID=2000000042`.

Бот сообщества **должен быть добавлен в беседу** вручную.

---

## Первый запуск (создание .session файла)

При первом запуске Telethon попросит номер телефона и код из Telegram:

```bash
cd /opt/news_relay
source .venv/bin/activate
python main.py
```

```
Please enter your phone (or bot token): +79001234567
Please enter the code you received: 12345
```

После успешного входа создастся файл `<TG_SESSION_NAME>.session`.
Бот начнёт слушать каналы. Остановить: `Ctrl+C`.

> **Важно:** файл `.session` — это ваша авторизованная сессия Telegram.
> Храните его в безопасном месте и не передавайте третьим лицам.

---

## Запуск через systemd (автозапуск на VPS)

### Создать системного пользователя

```bash
sudo useradd -r -s /bin/false -d /opt/news_relay newsrelay
sudo chown -R newsrelay:newsrelay /opt/news_relay
```

### Установить юнит

```bash
sudo cp news-relay.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable news-relay
sudo systemctl start news-relay
```

### Проверить статус

```bash
sudo systemctl status news-relay
sudo journalctl -u news-relay -f   # live-лог
```

### Перезапустить после изменения .env

```bash
sudo systemctl restart news-relay
```

---

## Структура проекта

```
news_relay/
├── main.py            # точка входа
├── tg_listener.py     # подписка на каналы Telegram
├── vk_sender.py       # отправка в VK API
├── filters.py         # фильтрация по ключевым словам
├── storage.py         # SQLite: дедупликация
├── config.py          # загрузка .env
├── requirements.txt
├── .env.example       # шаблон конфига
├── news-relay.service # systemd-юнит
└── README.md
```

---

## Бэкап данных

Критичные файлы для резервного копирования:

| Файл | Что хранит |
|---|---|
| `<session_name>.session` | Авторизация Telegram (user-сессия) |
| `news_relay.db` | ID отправленных постов (дедупликация) |
| `.env` | Все секреты и настройки |

Пример бэкапа через cron:

```bash
# /etc/cron.daily/news-relay-backup
tar -czf /root/backups/news_relay_$(date +%Y%m%d).tar.gz \
    /opt/news_relay/.env \
    /opt/news_relay/*.session \
    /opt/news_relay/news_relay.db
```

---

## Переменные окружения

| Переменная | Обязательная | Описание |
|---|---|---|
| `TG_API_ID` | ✅ | API ID с my.telegram.org |
| `TG_API_HASH` | ✅ | API Hash с my.telegram.org |
| `TG_SESSION_NAME` | — | Имя файла сессии (по умолчанию `news_relay_session`) |
| `TG_CHANNELS` | ✅ | Каналы через запятую (`@username` или ссылка) |
| `VK_TOKEN` | ✅ | Токен сообщества ВК |
| `VK_PEER_ID` | ✅ | peer_id беседы (2000000000 + chat_id) |
| `KEYWORDS` | — | Ключевые слова через запятую; пусто = пересылать всё |
| `LOG_FILE` | — | Файл лога (по умолчанию `news_relay.log`) |
| `LOG_LEVEL` | — | Уровень лога: DEBUG/INFO/WARNING (по умолчанию INFO) |

---

## Устранение проблем

**Бот не пересылает сообщения из закрытых каналов**
Убедитесь, что user-аккаунт (чья сессия используется) является **подписчиком** этих каналов.

**Ошибка VK API 7 (нет прав)**
Проверьте, что у токена сообщества включено право **Сообщения**, и что бот добавлен в беседу.

**Ошибка VK API 9 (flood)**
VK ограничивает частоту сообщений. Снизьте количество каналов или добавьте `KEYWORDS` для фильтрации.

**Файл сессии устарел / требует повторного входа**
Удалите `*.session` файл и запустите `python main.py` вручную для повторной авторизации.
