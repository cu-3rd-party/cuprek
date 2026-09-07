# circlebot

Telegram-бот, который следит за матом в чатах и в ответ иногда присылает
заранее одобренный **видео-кружок** (`video_note`). Плюс «предложка»: пользователи
присылают боту свои кружки, модераторы принимают/отклоняют их кнопками.

## Как работает

### Реакция на мат

* Бот читает все сообщения в группах, куда добавлен (нужен выключенный privacy mode).
* Каждое сообщение проверяется на русский/английский мат — с учётом обфускации
  (`б л и н`, `б.л.и.н.`, `блииин`, `бл*н`, `блиН`, `blin`, `p a n c a k e`, `p4ncake`, …).
* Счётчик матных сообщений ведётся отдельно **на каждую пару (чат, пользователь) за день**
  (граница суток — по `TIMEZONE`, по умолчанию МСК). Считаются сообщения, а не количество
  мата в них.
* Пока матных сообщений `≤ PROFANITY_FREE_MESSAGES` (по умолчанию 3) — ничего не происходит.
* Начиная со следующего сообщения бросается «кубик»:

  ```
  шанс(%) = PROFANITY_BASE_CHANCE + (счётчик - (FREE + 1)) * PROFANITY_STEP   (максимум 100)
  ```

  При дефолтах: 4-е сообщение — 1%, 5-е — 1.5%, 6-е — 2%, … 202-е — 100%.
* Если шанс срабатывает, бот отвечает на сообщение случайным кружком из базы.
  После этого пользователь **на сегодня в этом чате больше не отслеживается** —
  один кружок в день на чат. В трёх разных чатах можно получить три кружка за день.

### Предложка

* Любой пользователь присылает боту **в личку** видео-кружок.
* Кружок уходит в закрытый чат модераторов (`MOD_CHAT_ID`) с кнопками
  **✅ Принять / ❌ Отклонить**. Нажимать могут только `ADMIN_IDS`.
* Принятый кружок попадает в общую базу и может выпасть как случайный.
* Автор получает уведомление о решении.
* Дубликаты (по `file_unique_id`) отклоняются автоматически.
* Больше `MAX_PENDING_PER_USER` кружков «на модерации» от одного пользователя не принимается.
* Кружки от `ADMIN_IDS` в личке добавляются в базу сразу (сид стартового набора),
  если `ADMIN_DM_AUTO_ACCEPT=true`.

## Стек

* Python 3.12, [aiogram 3](https://docs.aiogram.dev) (long polling)
* PostgreSQL 16, SQLAlchemy 2.0 (async) + asyncpg, миграции Alembic
* Детектор мата — свой, на нормализации + curated-regex из `data/*.txt` (без ML-зависимостей)
* Docker + docker-compose

## Быстрый старт

1. **Создать бота** у [@BotFather](https://t.me/BotFather):
   * `/newbot` → получить токен;
   * `/setprivacy` → **Disable** (иначе бот не видит обычные сообщения в группах;
     как альтернатива — сделать бота админом каждой группы).

2. **Создать закрытую группу модераторов**, добавить туда бота. Узнать её `chat_id`:
   отправить в этой группе команду `/id` (бот ответит `chat_id`, начинается с `-100`).
   Свой `user_id` — тоже из `/id` в личке с ботом.

3. **Заполнить `.env`** (за основу — `.env.example`):

   ```dotenv
   BOT_TOKEN=...
   ADMIN_IDS=11111111,22222222
   MOD_CHAT_ID=-1001234567890
   ```

4. **Запустить**:

   ```bash
   docker compose up -d --build
   docker compose logs -f bot     # видно "applying database migrations" и старт polling
   ```

5. **Наполнить базу кружков**: администратор (`ADMIN_IDS`) отправляет боту в личку
   несколько видео-кружков — они сразу попадают в базу.

6. Добавить бота в рабочие чаты.

## Разработка

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# быстрые юнит-тесты (без БД)
pytest tests/test_chance.py tests/test_profanity.py

# полный набор — поднять Postgres и указать на него
docker compose up -d postgres
export TEST_DATABASE_URL=postgresql+asyncpg://bot:bot@localhost:5432/circlebot
pytest

ruff check src tests
```

Запуск бота локально (нужен доступный Postgres и `.env` в корне):

```bash
export DATABASE_URL=postgresql+asyncpg://bot:bot@localhost:5432/circlebot
alembic upgrade head
python -m circlebot
```

### Настройка детектора мата

Списки и regex-паттерны — в `data/`:

| файл | что это |
|---|---|
| `ru_squeezed.txt` | корни RU-мата без границ слова (ловят разбивку типа `с л о в о`, `с.л.о.в.о`) |
| `ru_spaced.txt`   | RU-паттерны с `\b` (для корней вроде `еб`, `бля`, `сук`) |
| `ru_translit.txt` | RU-мат латиницей (`nahuy`, `pizdec`) |
| `ru_whitelist.txt`| исключения (`страхуй`, `психуй`, …) |
| `en_squeezed.txt` / `en_spaced.txt` / `en_whitelist.txt` | то же для английского |

После правки — перезапустить бота (`docker compose restart bot`). Изменения желательно
закрывать тестами в `tests/test_profanity.py`.

## Структура

```
src/circlebot/
  __main__.py          точка входа (Bot + Dispatcher + polling)
  config.py            настройки из .env (pydantic-settings)
  db/                  models, engine, repo (запросы)
  services/
    profanity.py       детектор мата
    chance.py          формула вероятности
    locks.py           KeyedLock — сериализация сценария по (chat, user)
  middlewares/
    db_session.py      AsyncSession на апдейт
  handlers/
    profanity_watch.py мат -> шанс -> кружок
    submissions.py     приём кружков в личке
    moderation.py      кнопки принять/отклонить
    common.py          /start, /id
migrations/            Alembic
data/                  словари/паттерны детектора
```

## Заметки по эксплуатации

* Один инстанс бота (polling). Гонки в сценарии «мат → кружок» закрыты in-process
  `KeyedLock` + условным `UPDATE ... WHERE circle_sent = false`. Для нескольких инстансов
  понадобятся advisory-локи Postgres.
* Старые строки `daily_activity` не чистятся автоматически — при желании добавить
  периодический `DELETE FROM daily_activity WHERE activity_date < current_date - 7`.
* `file_id` кружков привязан к токену бота: при смене токена базу кружков нужно наполнить заново.
