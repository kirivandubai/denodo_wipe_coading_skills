# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это за репозиторий

Публичный плагин Claude Code — набор навыков (skills), позволяющих ИИ-агентам создавать
объекты в платформе Denodo, описывая намерение обычным текстом. Репозиторий
одновременно является плагином и маркетплейсом для него.

Remote: `github.com/kirivandubai/denodo_wipe_coading_skills` (имя на GitHub отличается от
имени локальной директории — учитывать в командах установки и в README).

**Дизайн-документ — единственный источник истины по архитектуре:**
`docs/superpowers/specs/2026-09-04-denodo-skills-design.md`. Перед любой работой над
навыками или скриптами читать его. Расхождение кода со спекой — это баг: либо в коде,
либо в спеке, и его надо устранить, а не оставить.

**Перечень объектов v1 — в отдельном документе:**
`docs/superpowers/specs/2026-09-04-denodo-v1-scope.md`. Шестнадцать объектов, для каждого
команда, навык, канал и способ верификации. Спека отвечает на вопрос «как устроено»,
этот документ — на вопрос «что именно входит».

**Текущая очередь работ — `docs/TASKS.md`.** Задача берётся оттуда, а не придумывается.

Слой исполнения (`scripts/denodo` + `scripts/denodo_cli/`) реализован в T5; готовы навыки `vql`, `execute`, `catalog`, `datasources`, `views`, `marketplace`, `procedures` (последний — вне объёма v1); beyond v1 since: `cache` (T27), `semantics` (T28), `metrics` (T29), `security` (T31), `ai` (T32), `dml` (T33), `materialize` (T34), `testing` (T35), `scheduler` (T36). Обе вехи закрыты приёмками: A — T13, B — T19. There is no `query` skill and no reference to one: the dialect is the table of silent deltas in the body of `vql` plus `skills/vql/references/dialect.md` (T24).
Юнит-тесты гоняются без зависимостей: `PYTHONPATH=scripts python3 -m unittest discover -s tests -t .`;
интеграционные — против стенда: `DENODO_TEST_ENV=dev uv run --with denodo-sqlalchemy
--with psycopg2-binary python -m unittest tests.integration.test_stand` (с `PYTHONPATH=scripts`).
Since T39 every `vql run` records what the session created in a ledger beside the profiles, and
`scripts/denodo vql plan <file>` / `api … --plan` say per statement whether the core's table lets the
agent apply it — a probe of yours, made in this session, is "own" to every subagent of the session:
create a fixture that must look like a colleague's with `DENODO_SESSION=<other>` in front of the command.
Прогон верификации шаблонов — `scripts/denodo verify --env lab`; the AI templates run only
with `--with-ai` (about 50 paid requests to the stand's LLM), the write templates of `dml` and
`materialize` only with `--with-writes` (`verify_` tables, a summary and a materialized table
created in the server's cache database and dropped in cleanup), the `.denodotest` templates of `testing`
only with `--testing-tool <dir>` (the Denodo Testing Tool installed there, Java on `PATH` or in
`JAVA_HOME`), the Scheduler templates of `scheduler` only with `--with-scheduler` (a `verify_`
project with two jobs, run and deleted; the export leaves its file in the Scheduler's export
folder). Since T40 the chain runs on any server: installation values are read from the server
(`@server`) or set in `~/.denodo/verify.toml` (one table per profile — the `lab` table points the
fixtures at a branch's own `verification/data` while its data is unmerged), a step whose
`requires` the server lacks is skipped with the reason, and every `verified`-marked block of
`skills/` is a step or a line of `[not_run]` (a unit test holds it). A new marked block needs one
of the two. Drop probe databases before a `--with-marketplace` run: its sync puts whatever VDP
has into the shared catalog. Сам инструмент:
`scripts/denodo --help`.

## Рабочий процесс

**Ветка на задачу, затем PR с описанием сделанного за сессию.**

1. Перед началом задачи — новая ветка от `main`. Именование: `<тип>/<краткая-суть>`,
   например `feat/execute-transport`, `docs/design-review`, `fix/vql-quoting`.
2. Работа коммитится в эту ветку. Прямые коммиты в `main` не делаются.
3. По завершении сессии — PR. **Описание PR излагает, что сделано за сессию**: какие
   решения приняты и почему, что проверено на живом стенде, что осталось незакрытым.
   Не перечисление файлов — их видно в диффе.
4. Если задача не закончена за сессию, PR всё равно создаётся как draft с честным
   разделом «что осталось».

## Инварианты, которые легко нарушить

Каждый пункт — следствие решения из спеки. Нарушение молча ломает либо срабатывание
навыков, либо безопасность.

- **Директории навыков не содержат префикса `denodo-`.** Плагин добавляет namespace сам:
  `skills/views/` → `/denodo:views`. Директория `denodo-views` даст `/denodo:denodo-views`.
- **Креденшелы никогда не попадают ни в репозиторий, ни в аргументы команд.** Профили
  сред лежат вне репозитория (`~/.denodo/profiles.toml`); в команде фигурирует только имя
  профиля, потому что аргументы `Bash` оседают в транскрипте сессии.
- **В репозитории нет клиентских данных**: ни реальных хостов, ни схем, ни имён систем.
  Плагин публичный.
- **Каждый шаблон несёт статус верификации** — `-- verified: 9.5 (live, дата)` или
  `-- unverified: 9.5 documentation only`. Шаблон без пометки считается непроверенным.
  Правило одинаково для VQL и для HTTP-вызовов маркетплейса.
- **Не всякий объект создаётся через VQL.** Data Marketplace — отдельный сервер платформы
  с REST API; его теги, категории и external elements живут в навыке `marketplace`.
  Теги VDP (`CREATE TAG`) и теги маркетплейса — **разные объекты**, и путать их нельзя:
  вызов уйдёт корректным, но не на тот сервер.
- **`scripts/denodo` (launcher) использует только стандартную библиотеку.** Он отвечает
  за настройку окружения и обязан работать до того, как зависимости установлены.
- **Целевая версия Denodo — только 9.5.** Развилок по версиям в шаблонах нет.
- **На стенде пишем только в свою базу.** Для проверок создаётся собственная база, и всё,
  что меняет состояние — `CREATE`, `ALTER`, `DROP`, любой DDL — идёт только в неё. Чужие
  базы **читаются свободно**: `SELECT`, `DESC`, `DESC VQL`, `GET_ELEMENTS()` — это лучший
  источник примеров синтаксиса, точнее документации. Ни одного изменяющего запроса за
  пределами своей базы, включая «безобидные» правки и уборку.
- **Scheduler objects are server-wide too** (T36). A Scheduler project, its jobs and their
  reports are seen by everyone on the Scheduler: probes and subagent fixtures live in a
  `zq<task>_` project and are deleted by that name; another team's project is read, never
  changed. A job runs as the login of its VDP data source and keeps running after the session —
  a probe job is created disabled, or deleted before the session ends.
- **Server-wide objects are yours by name only** (T31). Users, roles, tags and global
  security policies belong to no database. For a check they are created under a prefix
  that names the run — `verify_` for the verification chain, `zq<task>_` for manual probes
  and subagent runs — and removed by that name when the work is done. Users for a check are
  `EXTERNAL`: no password exists to leak, and impersonation reads as them. Existing
  server-wide objects are read freely and never changed, the profile's own user included;
  the one standing exception is the `impersonator` role the owner granted to `admin` on the
  stand, which the policy checks of `security` and of `verify` stand on.
- **AI calls on the stand are paid by the owner** (T32). Every `…_AI` function, `EMBED_AI` and
  `VECTOR_DISTANCE` with a text sends one request per row to the stand's LLM provider. Probes
  and subagent scenarios run them only over views of a few hundred rows at most — a fixture,
  or a small demo view — and a subagent prompt names the only databases it may read.
- **Source databases on the stand are written only in tables of the run** (T33). A write
  through Denodo lands in SQL Server or PostgreSQL, outside every Denodo database: the `verify`
  chain creates and drops its own `verify_` tables; a probe or a subagent fixture that needs a
  table creates a `zq<task>_` one through Denodo itself (`CREATE REMOTE TABLE` through a data
  source of your own database, reusing an existing source's ciphertext — no password is read)
  only after the owner's yes for that task, and drops it at the end
  (`CREATE_REMOTE_TABLE` with `replace_remote_table_if_exist`, then `DROP_REMOTE_TABLE`).
  Tables of other teams are read freely and never written to. Over the tool's connection
  `ROLLBACK` undoes nothing, so a probe write is a real write.

## Проверки

- **CI and the lint of the skills** (T38) — `.github/workflows/ci.yml` runs the unit tests and
  `claude plugin validate .` on every pull request. The lint is `tests/skills_lint.py`, part of
  the unit tests: Cyrillic, names of the test server, task ids and "v1", description budget
  (900) and `SKILL.md` length, marks, links. Its lists (`OVER_BUDGET`, `LONG_SKILLS`,
  `UNMARKED_BLOCKS`) change only with a reason a reviewer sees; a new name of the stand that
  reaches a skill goes into `INSTALLATION_NAMES`.
- **Верификация шаблонов** — прогоняются на живом стенде в отдельной тестовой базе;
  результат обновляет пометки `verified:`. Синтаксис источников проверяется без самих
  источников: недоступный хост всё равно проходит парсер Denodo.
- **Eval-сьют навыков** (`evals/`) — проверяет, что на заданную фразу срабатывает нужный
  навык: `claude plugin eval . --ablation none` из корня репозитория (устанавливать плагин
  для этого не нужно, он резолвится по пути). Обязателен к прогону при добавлении навыка
  или изменении любого `description`: описания конкурируют между собой, и деградация иначе
  проходит незаметно. Устройство кейсов и разбор падений — в [`evals/README.md`](evals/README.md).
