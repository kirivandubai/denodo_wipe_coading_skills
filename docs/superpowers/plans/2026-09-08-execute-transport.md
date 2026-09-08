# T5 «Слой исполнения `scripts/denodo`» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Цель:** команда `scripts/denodo`, которой навыки применяют VQL к живому VDP и REST-вызовы
к Data Marketplace, с профилями сред и JSON-выводом.

**Архитектура:** launcher на stdlib поднимает окружение (uv → venv → подсказка) и
запускает пакет `denodo_cli`; внутри — профили, разбиение VQL на выражения,
классификация разрушительных операций и два транспорта (`vql_psycopg2`, `api_rest`) за
общим интерфейсом. Все команды печатают один JSON-документ на stdout.

**Стек:** Python ≥ 3.11 (tomllib), `denodo-sqlalchemy>=2.0.5`, `psycopg2-binary>=2.9.6`,
тесты — `unittest` из stdlib, чтобы гоняться без зависимостей.

**Спека:** `docs/superpowers/specs/2026-09-04-denodo-skills-design.md`, раздел 7; вводные
из отчётов спайков T2 (раздел 3) и T11 (раздел 2).

## Глобальные ограничения

- `scripts/denodo` — только стандартная библиотека (спека 7.2).
- Креденшелы никогда не в аргументах команд; в команде — только имя профиля (7.4).
- Профили вне репозитория: `~/.denodo/profiles.toml`, переопределяется `DENODO_PROFILES` (7.4).
- Профиль несёт `production`; вывод каждой команды показывает его (7.4).
- Вывод машиночитаемый: один JSON-документ на stdout, диагностика — stderr (7.4).
- Транспорты за общим интерфейсом; новый транспорт — файл плюс строка профиля (7.3).
- Язык публичных артефактов (help, сообщения, ключи JSON, комментарии в `scripts/`) — английский (T4).
- Целевая версия Denodo — 9.5; клиентских данных в репозитории нет.

## Решения, закрывающие открытые места спеки

1. **Профиль** (формат из спайков плюс два поля):
   `host, port=9996, database="admin", user, password | password_env, production=false,
   transport="vql_psycopg2", marketplace_url?, marketplace_server_id?`.
2. **Многовыражённый файл** режется на выражения клиентом (по `;` вне строк и
   комментариев) и исполняется по одному; при ошибке остановка, в ответе — индекс и
   текст упавшего выражения. Поведение сервера при ошибке в середине одной строки с
   `;` проверяется на стенде и записывается в отчёт, но на него не опираемся.
3. **Команды v1:** `vql run`, `vql desc`, `api <method>`, `env init|list|check`.
   `verify` появляется в T12 вместе с форматом шаблонов.
4. **Безопасность на уровне инструмента:** `safety.classify_vql` / `classify_http`
   помечают разрушительные операции; в JSON есть `destructive: true`, а в профиле с
   `production = true` такие операции требуют флага `--allow-destructive`. Правило 6.3
   (подтверждение человека) остаётся в ядре T6, инструмент лишь не даёт выполнить его молча.
5. **`env init` интерактивна** (getpass), запускается человеком через `! scripts/denodo env init`,
   пароль в транскрипт не попадает.

## Структура файлов

```
scripts/denodo                          launcher
scripts/denodo_cli/__init__.py          версия
scripts/denodo_cli/__main__.py          PEP 723 метаданные, sys.path, main()
scripts/denodo_cli/cli.py               argparse, диспетчер, JSON-вывод, коды выхода
scripts/denodo_cli/output.py            конверт ответа, сериализация строк
scripts/denodo_cli/profiles.py          загрузка/валидация профилей, redaction, init
scripts/denodo_cli/vql_split.py         разбиение VQL на выражения
scripts/denodo_cli/safety.py            классификация разрушительных операций
scripts/denodo_cli/errors.py            нормализация текста ошибок psycopg2
scripts/denodo_cli/transports/__init__.py  реестр по имени
scripts/denodo_cli/transports/base.py      контракт
scripts/denodo_cli/transports/vql_psycopg2.py
scripts/denodo_cli/transports/vql_flightsql.py  заглушка «не в v1»
scripts/denodo_cli/transports/api_rest.py
scripts/denodo_cli/commands/vql.py, api.py, env.py
tests/test_*.py                         unittest, без стенда
tests/integration/test_stand.py         только при DENODO_TEST_ENV
```

Коды выхода: `0` — успех, `1` — ошибка исполнения (сервер отказал), `2` — ошибка
конфигурации или вызова, `3` — окружение не поднято (launcher).

---

### Task 1: разбиение VQL на выражения (`vql_split.py`)

**Files:** Create `scripts/denodo_cli/vql_split.py`, `scripts/denodo_cli/__init__.py`; Test `tests/test_vql_split.py`.

**Produces:** `split_statements(text: str) -> list[str]` — выражения без завершающего `;`
и без пустых; учитывает `'...'` c `''`, `"..."`, комментарии `--`, `#`, `/* */`.

- [ ] Тест: два выражения через `;`; `;` внутри строки; `;` в комментариях трёх видов;
  пустой хвост после последнего `;`; выражение без `;`.
- [ ] Запустить `python3 -m unittest tests.test_vql_split -v` — FAIL (ImportError).
- [ ] Реализовать посимвольный сканер состояний.
- [ ] Прогнать — PASS. Коммит `feat(cli): split VQL text into statements`.

### Task 2: профили сред (`profiles.py`)

**Files:** Create `scripts/denodo_cli/profiles.py`; Test `tests/test_profiles.py`.

**Produces:** `@dataclass Profile(name, host, port, database, user, password, production,
transport, marketplace_url, marketplace_server_id)`, `load_profile(name, path=None) -> Profile`,
`profiles_path() -> Path`, `list_profiles(path=None) -> list[dict]` (без паролей),
`ProfileError(Exception)`, `write_profile(path, profile)`.

- [ ] Тесты: загрузка минимального профиля с дефолтами; `password_env`; отсутствие
  файла / профиля / обязательных полей → `ProfileError` с понятным текстом;
  `DENODO_PROFILES` переопределяет путь; `list_profiles` не содержит пароля;
  `write_profile` дописывает секцию, не трогая существующие, права `0600`.
- [ ] FAIL → реализация на `tomllib` (чтение) и ручной TOML-записи (секция из
  строк и чисел) → PASS. Коммит `feat(cli): environment profiles`.

### Task 3: классификация разрушительных операций (`safety.py`)

**Files:** Create `scripts/denodo_cli/safety.py`; Test `tests/test_safety.py`.

**Produces:** `classify_vql(statement) -> str | None` (`"drop" | "alter" | None`),
`classify_http(method, path, body) -> str | None`.

- [ ] Тесты VQL: `DROP ...`, `DROP ... IF EXISTS`, `ALTER VIEW` → помечены;
  `CREATE OR REPLACE` — нет (это идемпотентный дефолт 6.4); `ALTER TAG ... ADD_TO` —
  `"alter"`; ведущие комментарии игнорируются; регистр.
- [ ] Тесты HTTP: любой `DELETE` → `"delete"`; `POST /public/api/tags/vdp/synchronize`,
  `POST .../element-management/all/synchronize`, `POST .../views/{id}/tags`,
  `POST .../views/{id}/categories` → `"replace"`; `POST /public/api/tags` → None;
  `GET` → None; путь с `serverId` в query.
- [ ] FAIL → реализация → PASS. Коммит `feat(cli): classify destructive operations`.

### Task 4: ошибки и конверт вывода (`errors.py`, `output.py`)

**Files:** Create `scripts/denodo_cli/errors.py`, `scripts/denodo_cli/output.py`; Test `tests/test_errors.py`, `tests/test_output.py`.

**Produces:** `normalize_error(exc: BaseException) -> dict{"message", "raw", "type"}` —
из текста psycopg2 вытаскивает фрагмент после `java.sql.SQLException:` в первой строке
`DETAIL:`; `envelope(ok, env: Profile|None, command, **fields) -> dict`,
`rows_payload(columns, rows, max_rows) -> dict{"columns","rows","row_count","truncated"}`
с приведением не-JSON типов к `str`.

- [ ] Тесты: текст ошибки с `DETAIL: java.sql.SQLException: Syntax error: ...` → `message`
  без префиксов; ошибка без `DETAIL` → `message == raw`; `rows_payload` режет по
  `max_rows` и ставит `truncated`; `Decimal`/`datetime` сериализуются; `envelope`
  содержит `env.production`.
- [ ] FAIL → реализация → PASS. Коммит `feat(cli): error normalisation and JSON envelope`.

### Task 5: контракт транспортов и реестр

**Files:** Create `scripts/denodo_cli/transports/__init__.py`, `base.py`, `vql_flightsql.py`; Test `tests/test_transports_registry.py`.

**Produces:** `base.VqlResult(statement, columns, rows, row_count)`, `base.VqlTransport`
(Protocol: `execute(statement) -> VqlResult`, `close()`), `transports.get_vql_transport(name) -> type`;
неизвестное имя → `KeyError` с перечнем; `vql_flightsql` — класс, чей `__init__`
бросает `NotImplementedError("flightsql transport is not part of v1")`.

- [ ] Тесты: реестр отдаёт `vql_psycopg2` лениво (модуль sqlalchemy не импортируется до
  вызова); неизвестное имя; flightsql не в v1.
- [ ] FAIL → реализация → PASS. Коммит `feat(cli): transport contract and registry`.

### Task 6: транспорт `vql_psycopg2`

**Files:** Create `scripts/denodo_cli/transports/vql_psycopg2.py`; Test `tests/integration/test_stand.py` (gated).

**Produces:** `VqlPsycopg2Transport(profile, database=None)`: движок `denodo+psycopg2`,
автокоммит через событие `connect` (T2 3.1), одно соединение на объект, `execute` через
сырой курсор psycopg2 без параметров (T2 3.2), `columns` из `cursor.description`,
`close()` → `engine.dispose()`.

- [ ] Интеграционный тест (пропускается без `DENODO_TEST_ENV`): `SELECT 1`, `%` в `LIKE`,
  `CREATE OR REPLACE FOLDER` в тестовой базе и `DROP`, ошибка синтаксиса → исключение с
  текстом сервера.
- [ ] Реализация; прогон на стенде `DENODO_TEST_ENV=dev`. Коммит `feat(cli): vql_psycopg2 transport`.

### Task 7: транспорт `api_rest`

**Files:** Create `scripts/denodo_cli/transports/api_rest.py`; Test `tests/test_api_rest.py` (локальный `http.server` в потоке) и раздел в `tests/integration/test_stand.py`.

**Produces:** `RestTransport(profile)`: `call(method, path, *, json_body=None, params=None,
multipart=None, timeout=300) -> HttpResult(status, body, headers, elapsed_ms)`; HTTP Basic
на каждом запросе, без cookie-jar; `serverId` из профиля подставляется, если задан и не
передан; `multipart: dict[field, (filename, bytes, content_type)]`; тело парсится как
JSON, иначе текст; ошибки HTTP не бросаются — статус отдельно от тела (T11 раздел 2).

- [ ] Тесты на локальном сервере: заголовок `Authorization`, `serverId` в query,
  JSON-тело, multipart с двумя частями, `409` с пустым телом → `body is None`,
  не-JSON тело → строка.
- [ ] FAIL → реализация на `urllib` → PASS. Коммит `feat(cli): api_rest transport`.

### Task 8: команды `vql run` / `vql desc` (`commands/vql.py`)

**Files:** Create `scripts/denodo_cli/commands/__init__.py`, `commands/vql.py`; Test `tests/test_commands_vql.py` (транспорт-фейк, внедряется через фабрику).

**Produces:** `run_vql(profile, statements, *, transport_factory, max_rows, allow_destructive,
continue_on_error) -> (dict, exit_code)`; `desc(profile, name, kind, vql: bool, ...)`.
Ответ `vql run`: `{"ok", "env", "command":"vql run", "statements":[{"index","statement","ok",
"destructive","columns","rows","row_count","truncated","error"}], "failed_at"}`.

- [ ] Тесты: два выражения → два результата; ошибка во втором из трёх → `ok:false`,
  `failed_at: 1`, третье не исполнялось; `continue_on_error` исполняет все;
  `DROP` на production без флага → отказ до вызова транспорта, код `2`;
  `DROP` на production с флагом — исполняется; `max_rows` обрезает.
- [ ] FAIL → реализация → PASS. Коммит `feat(cli): vql run and vql desc commands`.

### Task 9: команды `api` и `env` (`commands/api.py`, `commands/env.py`)

**Files:** Create `commands/api.py`, `commands/env.py`; Test `tests/test_commands_api.py`, `tests/test_commands_env.py`.

**Produces:** `api_call(profile, method, path, *, json_body, params, multipart, timeout,
allow_destructive, transport_factory) -> (dict, exit_code)`; ответ
`{"ok": 2xx, "status", "body", "destructive", "elapsed_ms", "env"}`; `DELETE` на production без
флага → код `2`. `env_list()`, `env_check(profile, transport_factories)` — `SELECT 1`
плюс `GET /Ping` маркетплейса, если `marketplace_url` задан; `env_init(io)` — вопросы через
переданные `input`/`getpass`, запись через `write_profile`.

- [ ] Тесты: маршрутизация статуса в `ok`; multipart-аргумент `field=@path` читает файл,
  `field=json:{...}` даёт JSON-часть; `env_init` с подменёнными вводами пишет секцию и не
  печатает пароль; `env_check` без `marketplace_url` не трогает REST.
- [ ] FAIL → реализация → PASS. Коммит `feat(cli): api and env commands`.

### Task 10: `cli.py`, `__main__.py`, коды выхода

**Files:** Create `scripts/denodo_cli/cli.py`, `scripts/denodo_cli/__main__.py`; Test `tests/test_cli.py` (через `cli.main(argv)` с перехватом stdout).

**Produces:** `main(argv) -> int`; подкоманды и флаги:
`vql run [FILE|-] [-e STMT] --env --database --max-rows --continue-on-error --allow-destructive`,
`vql desc NAME --env [--type view|table|datasource df|...] [--vql]`,
`api METHOD PATH --env [--json STR|--json-file F] [--param k=v]* [--part field=@f|json:...]* [--timeout N] [--allow-destructive]`,
`env init|list|check [--env]`. `--env` берётся из `DENODO_ENV`, если не задан. Любое
исключение конфигурации → JSON `{"ok":false,"error":{"kind":"config",...}}`, код `2`.

- [ ] Тесты: `env list` печатает JSON; отсутствие `--env` → код `2` и JSON-ошибка;
  неизвестный профиль → код `2`; `vql run -e` на фейковом транспорте → код `0`.
- [ ] FAIL → реализация → PASS. Коммит `feat(cli): argument parser and entry point`.

### Task 11: launcher `scripts/denodo`

**Files:** Create `scripts/denodo` (исполняемый); Test `tests/test_launcher.py`.

**Produces:** исполняемый Python-файл, stdlib. Порядок: `DENODO_CLI_PYTHON` задан → запустить
им `-m denodo_cli` с `PYTHONPATH=scripts`; иначе `uv` в `PATH` → `uv run -q --script
scripts/denodo_cli/__main__.py ARGS`; иначе venv в `${CLAUDE_PLUGIN_DATA:-~/.claude/plugins/data/denodo}/venv`
(создать, `pip install` зависимостей из PEP 723-блока `__main__.py`, штамп с хэшем
зависимостей); не вышло → JSON `{"ok":false,"error":{"kind":"environment",
"hint":"<точная команда установки>"}}`, код `3`. Зависимости читаются из `__main__.py`
регуляркой из PEP 723 — единственный источник.

- [ ] Тесты: `read_inline_dependencies(path)` парсит блок; выбор стратегии по подменённым
  `shutil.which`/env; запуск `scripts/denodo env list` через subprocess с
  `DENODO_CLI_PYTHON=sys.executable` возвращает JSON.
- [ ] FAIL → реализация → PASS → `chmod +x`. Коммит `feat(cli): stdlib launcher`.

### Task 12: проверка на стенде, документация, трекер

- [ ] Прогнать `DENODO_TEST_ENV=dev python3 -m unittest discover -s tests` в окружении
  `uv run`; прогнать вручную: `scripts/denodo env check --env dev`, файл `.vql` с ошибкой в
  середине, `api get /public/api/tags/count`, `api post` с multipart (тип провайдера с
  последующим удалением), `DROP` через профиль-копию с `production = true`.
- [ ] Отдельно снять поведение сервера при ошибке в середине одной строки с `;`.
- [ ] Обновить спеку: 7.3 — реальные команды, 7.4 — формат профиля; `docs/TASKS.md` —
  T5 в «Сделано», T7 в «Дальше», вводные для T7/T12; `.gitignore` без изменений.
- [ ] Коммит `docs: T5 closed, profile format fixed in spec`, PR.
