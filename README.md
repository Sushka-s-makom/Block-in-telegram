# Block_tg

Telegram-бот и веб-панель на FastAPI для проверки, заблокировал ли вас другой пользователь в Telegram.

## Стек

- Python 3.11+
- Telethon
- FastAPI
- Uvicorn
- SQLite
- python-dotenv

## Что умеет проект

- запускает Telegram-бота как точку входа;
- открывает веб-панель по подписанной ссылке;
- подключает пользовательский аккаунт Telegram через телефон, код и 2FA;
- сохраняет `StringSession` в SQLite;
- проверяет блокировку через смену темы чата или короткий звонок.

## Структура проекта

```text
.
├── app/
│   ├── bot.py                 # логика Telegram-бота
│   ├── webapp.py              # FastAPI-приложение
│   ├── config.py              # загрузка настроек и пути
│   ├── logging_utils.py       # настройка логов
│   ├── core/
│   │   ├── checker.py         # проверка блокировки
│   │   └── panel_links.py     # подпись ссылок в панель
│   └── db/
│       └── storage.py         # работа с SQLite
├── scripts/
│   ├── generate_bot_string_session.py
│   └── generate_user_string_session.py
├── session/
│   └── users/
├── main.py                    # точка входа для бота
├── webapp.py                  # импорт FastAPI app для uvicorn
├── requirements.txt
└── README.md
```

## Установка

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Переменные окружения

Создайте `.env` и заполните:

```env
API_ID=
API_HASH=
BOT_TOKEN=
WEB_APP_URL=http://127.0.0.1:8000
APP_SECRET=your-long-random-secret
BOT_STRING_SESSION=
PROXY_URL=
```

## Запуск

В двух терминалах:

```bash
.venv/bin/python main.py
```

```bash
.venv/bin/uvicorn webapp:app --host 0.0.0.0 --port 8000
```

## Полезные скрипты

Сгенерировать пользовательскую `StringSession`:

```bash
.venv/bin/python scripts/generate_user_string_session.py
```

Сгенерировать `StringSession` для бота:

```bash
.venv/bin/python scripts/generate_bot_string_session.py
```

## Как работает

1. Пользователь открывает бота и получает ссылку на панель.
2. Панель подписывается через `HMAC-SHA256`, чтобы ссылку нельзя было подделать.
3. Пользователь подключает свой Telegram-аккаунт.
4. Сессия сохраняется в `block_checker.db`.
5. Проверка выполняется от имени подключённого аккаунта, а не от имени бота.

## Примечания

- Бот и веб-панель должны работать одновременно.
- SQLite и директория `session/` используются обоими процессами совместно.
- Для production лучше вынести панель на публичный домен и добавить нормальную аутентификацию.
