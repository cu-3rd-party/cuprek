# CuprekBot

Тгбот, который следит за матом в чатах и в ответ иногда присылает
заранее одобренный **круок**. Пользователи присылают боту свои кружки, модераторы принимают/отклоняют их кнопками.

## Как работает

### Реакция на мат

* Бот читает все сообщения в группах, куда добавлен.
* Каждое сообщение проверяется на русский/английский мат — с учётом обфускации
  (`б л и н`, `б.л.и.н.`, `блииин`, `бл*н`, `блиН`, `blin`, `p a n c a k e`, `p4ncake`, …).
* Счётчик матных сообщений ведётся отдельно на каждую пару (чат, пользователь) за день
  (граница суток — по `TIMEZONE`, по умолчанию МСК). Считаются сообщения, а не количество
  мата в них.
* Пока матных сообщений немного, ничего не происходит, но если начинается превышение...
* Начиная со следующего сообщения роллится шанс:

  ```
  шанс(%) = PROFANITY_BASE_CHANCE + (счётчик - (FREE + 1)) * PROFANITY_STEP, кап на 100%
  ```

  По дефолту 4-е сообщение - 1%, 5-е - 1.5%, 6-е - 2%, ...
* Если шанс срабатывает, бот отвечает на сообщение случайным кружком из базы.
  После этого пользователь на сегодня в этом чате больше не отслеживается —
  один кружок в день на чат. В трёх разных чатах можно получить три кружка за день.
* Для user-id из `GUARANTEED_CIRCLE_IDS` кружок приходит на КАЖДОЕ матное
  сообщение — в обход `PROFANITY_FREE_MESSAGES`, шанса и капа «один кружок в день
  на чат». `ALLOWED_CHAT_IDS` для них по-прежнему действует.

### Предложка

* Любой пользователь присылает боту в личку кружок.
* Кружок уходит в закрытый чат модераторов с кнопками принять/отклонить.
* Принятый кружок попадает в общую базу и может выпасть как случайный.
* Автор получает уведомление о решении.
* Дубликаты отклоняются автоматически.
* Больше `MAX_PENDING_PER_USER` кружков «на модерации» от одного пользователя не принимается.
* Кружки от `ADMIN_IDS` в личке добавляются в базу сразу (сид стартового набора),
  если `ADMIN_DM_AUTO_ACCEPT=true`.

### Управление кружками (только `ADMIN_IDS`, в личке с ботом)

* `/circles` — бот присылает каждый активный кружок с кнопкой **🗑 Удалить кружок**
  (до 20 за раз, новые сверху). Удаление мягкое: `is_active=false`, кнопка меняется на
  **♻️ Вернуть кружок**.
* `/circles all` — то же, но вместе с уже удалёнными (у них кнопка ♻️).
* `/rmcircle <id>` — удалить кружок по номеру из `/circles`.
* `/status` — состояние деплоя: аптайм, `@username` и id бота, версия сборки (`GIT_SHA`),
  пинг базы, счётчики кружков и заявок, возраст heartbeat. Проверить сервер с телефона,
  не заходя по ssh.
* На карточке модерации у принятого кружка тоже есть кнопка 🗑 — модератор может
  откатить своё «Принять».

### Управление доступом (только админ, в личке с ботом)

Списки админов и «гарантированных» правятся прямо из телеги — редактировать `.env`
и пересобирать контейнер больше не нужно.

* `/admins` — показать список; `/admins add 111 222` — добавить; `/admins rm 111` — убрать.
* `/guaranteed` — то же для списка тех, кому кружок приходит на каждое матное сообщение.
* Id можно перечислять через пробел или запятую. Свой id — из `/id`.

Значения из `.env` (`ADMIN_IDS`, `GUARANTEED_CIRCLE_IDS`) остаются **неудаляемыми**
(в списке помечены 🔒): иначе админ мог бы снести всех админов, включая себя, и вернуть
доступ можно было бы только через `psql` на сервере. Всё, что добавлено командой, лежит
в таблице `managed_ids` и переживает рестарт контейнера.

## Стек

* Python 3.12, [aiogram 3](https://docs.aiogram.dev) (long polling)
* PostgreSQL 16, SQLAlchemy 2.0 (async) + asyncpg, миграции Alembic
* Детектор мата — свой, на нормализации + curated-regex из `data/*.txt` (без ML-зависимостей)
* Docker + docker-compose

## Быстрый старт

1. **Создать бота** у [@BotFather](https://t.me/BotFather):
   * `/newbot` - получить токен;
   * `/setprivacy` - **Disable** (иначе бот не видит обычные сообщения в группах)

2. **Создать закрытую группу модераторов**, добавить туда бота. Узнать её `chat_id`:
   отправить в этой группе команду `/id` (бот ответит `chat_id`, начинается с `-100`).
   Свой `user_id` — тоже из `/id` в личке с ботом.

3. **Заполнить `.env`** (за основу — `.env.example`):

   ```dotenv
   BOT_TOKEN=...
   ADMIN_IDS=11111111,22222222
   MOD_CHAT_ID=-1001234567890
   # на сервере обязательно задать свой — иначе используется дефолтный `bot`
   POSTGRES_PASSWORD=...
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

# полный набор — поднять Postgres (repo-тесты создадут отдельную БД circlebot_test).
# Порт 5432 наружу открывает только dev-оверлей, в базовом compose его нет.
# Если 5432 уже занят другим проектом -- задать DEV_PG_PORT.
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres
export DATABASE_URL=postgresql+asyncpg://bot:$POSTGRES_PASSWORD@localhost:${DEV_PG_PORT:-5432}/circlebot
pytest

ruff check src tests
```

Запуск бота локально (нужен доступный Postgres и `.env` в корне):

```bash
export DATABASE_URL=postgresql+asyncpg://bot:$POSTGRES_PASSWORD@localhost:5432/circlebot
alembic upgrade head
python -m circlebot
```

### Обновление зависимостей

`pyproject.toml` — источник правды для диапазонов версий, `requirements.txt` —
зафиксированный результат их разрешения (его и ставит Dockerfile, поэтому сборка
воспроизводима и слой с зависимостями кэшируется). После правки зависимостей в
`pyproject.toml` пересобрать лок в контейнере, чтобы пины соответствовали Linux:

```bash
docker run --rm -v "$PWD":/w -w /w python:3.12-slim-bookworm \
  sh -c "pip install -q uv && uv pip compile pyproject.toml -o requirements.txt"
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
  logging.py           формат логов (всегда UTC, суффикс Z)
  health.py            `python -m circlebot.health` — healthcheck контейнера
  db/                  models, engine, repo (запросы)
  services/
    profanity.py       детектор мата
    chance.py          формула вероятности
    locks.py           KeyedLock — сериализация сценария по (chat, user)
    alerts.py          WARNING+ из логов -> чат модераторов
    heartbeat.py       пинг БД + heartbeat-файл для healthcheck
  middlewares/
    db_session.py      AsyncSession на апдейт
  handlers/
    profanity_watch.py мат -> шанс -> кружок
    submissions.py     приём кружков в личке
    moderation.py      кнопки принять/отклонить
    circles.py         /circles, /rmcircle, удаление/возврат кружков
    common.py          /start, /id
    status.py          /status — состояние деплоя
migrations/            Alembic
data/                  словари/паттерны детектора
```

## Деплой на сервер

Сборка идёт прямо на сервере, реестр не нужен. Нужен только Docker с compose v2
(`docker compose version`; для длинной формы `env_file:` требуется ≥ 2.24).

```bash
git clone <repo> cuprek && cd cuprek
cp .env.example .env && nano .env     # BOT_TOKEN, ADMIN_IDS, MOD_CHAT_ID, POSTGRES_PASSWORD

GIT_SHA=$(git rev-parse --short HEAD) docker compose up -d --build
docker compose ps                     # bot должен стать healthy в течение ~1 минуты
docker compose logs -f bot
```

`GIT_SHA` необязателен, но с ним `/status` показывает, какая сборка сейчас живая.
Удобно завернуть обновление в скрипт:

```bash
git pull
GIT_SHA=$(git rev-parse --short HEAD) docker compose up -d --build
docker image prune -f                 # подчистить повисшие слои прошлой сборки
```

Проверить, что всё живо, не заходя в логи:

```bash
docker compose ps                     # healthy / unhealthy по heartbeat-файлу
docker compose exec bot python -m circlebot.health
docker stats --no-stream              # фактическое потребление памяти
```

Что уже настроено, чтобы сервис не разрастался и не падал молча:

* **Логи ограничены** — 10 МБ × 5 файлов на контейнер, иначе `json-file` растёт
  бесконечно и со временем забивает диск.
* **Имя проекта зафиксировано** (`name: cuprek` в compose), поэтому том всегда
  `cuprek_pgdata` независимо от имени каталога с чекаутом — новый пустой том при
  переносе не появится.
* **Postgres не публикует порт наружу** — только внутренняя сеть compose. Для доступа
  из шелла: `docker compose exec postgres psql -U bot circlebot`.
* **Лимиты памяти** — 512 МБ на бота, 512 МБ на Postgres, и `max_connections=30`
  вместо стоковой сотни. Бот в покое занимает ~178 МБ, из них ~121 МБ — сам aiogram
  (он строит pydantic-модели на весь Telegram API при импорте); лимит стоит с запасом
  на всплески, а не впритык.
* **Слой зависимостей кэшируется и запинен** (`requirements.txt`) — правка кода
  пересобирает образ за ~12 секунд вместо минуты, и одна и та же ревизия всегда
  собирается с одними и теми же версиями пакетов.
* **Образ не от root** — процесс идёт под uid 10001.
* **Healthcheck по heartbeat** — бот раз в `HEARTBEAT_INTERVAL` секунд пингует
  Postgres и трогает файл; если событийный цикл завис или база отвалилась,
  контейнер уходит в `unhealthy`, даже если процесс формально жив.
* **Алерты в Telegram** — записи уровня `ALERT_LEVEL` и выше дублируются в
  `ALERT_CHAT_ID` (по умолчанию `MOD_CHAT_ID`), так что о поломке видно без ssh.
* Бэкап базы: `docker compose exec -T postgres pg_dump -U bot circlebot > dump.sql`.

### Чтение логов удалённо

Всё пишется в stdout, файлов с логами нет — только `docker compose logs`.
**Время всегда UTC и помечено суффиксом `Z`**: сервер обычно живёт в UTC, а «сутки»
бота считаются по `TIMEZONE`, и без пометки эти два времени не различить.

```bash
docker compose logs -f bot                  # хвост в реальном времени
docker compose logs --since 1h bot          # за последний час
docker compose logs --tail 200 bot          # последние 200 строк
docker compose logs --since 24h bot | grep -E 'WARNING|ERROR|CRITICAL'
docker compose logs bot | grep 'circle='    # что, кому и с каким шансом улетело
```

Нормальный старт — три строки, по которым видно всё существенное:

```
2026-09-07 20:33:50Z INFO     __main__: starting bot=@cuprekbot id=123456 build=80bade9 circles=42 admins=[111] mod_chat=-100... watched_chats=all tz=Europe/Moscow
2026-09-07 20:33:50Z INFO     __main__: log alerts -> chat=-100... at WARNING
2026-09-07 20:33:50Z INFO     __main__: polling started
```

Ошибки конфигурации — одна понятная строка вместо трейсбека в цикле рестартов:

| строка в логе | что делать |
|---|---|
| `BOT_TOKEN is invalid — Telegram rejected it as Unauthorized` | проверить `BOT_TOKEN` |
| `database unreachable at startup: ...` | проверить `POSTGRES_PASSWORD` и `docker compose ps postgres` |
| `circle pool is empty` | админу отправить боту кружки в личку |
| `heartbeat: database unreachable` | база отвалилась, контейнер уйдёт в `unhealthy` |

Штатная остановка логируется явно, поэтому рестарт не выглядит как падение:

```
2026-09-07 20:40:11Z INFO     __main__: received SIGTERM, shutting down
2026-09-07 20:40:11Z INFO     __main__: polling stopped
2026-09-07 20:40:11Z INFO     __main__: shutdown complete
```

Записи уровня `ALERT_LEVEL` и выше дополнительно уходят в `ALERT_CHAT_ID` — с
дедупликацией и лимитом на частоту, чтобы цикл падений не превратился во флуд;
подавленные повторы приезжают счётчиком `(+N more suppressed)`.

## Заметки по эксплуатации

* Один инстанс бота (polling). Гонки в сценарии «мат → кружок» закрыты in-process
  `KeyedLock` + условным `UPDATE ... WHERE circle_sent = false`. Для нескольких инстансов
  понадобятся advisory-локи Postgres.
* Старые строки `daily_activity` не чистятся автоматически — при желании добавить
  периодический `DELETE FROM daily_activity WHERE activity_date < current_date - 7`.
* `file_id` кружков привязан к токену бота: при смене токена базу кружков нужно наполнить заново.
