# Denodo Skills: набор навыков для создания объектов Denodo через ИИ-агентов

**Дата:** 2026-09-04
**Статус:** дизайн утверждён; реализация идёт — слой исполнения (раздел 7) сделан в T5, навык `execute` — в T7, ядро `/denodo:vql` (раздел 6) — в T6, доменные навыки `catalog` (T8a), `datasources` (T8b), `views` (T8c) и `marketplace` (T8d) — по разделу 8. `query` was not built as a skill: the owner's roadmap review (2026-09-29) made the
dialect a reference in `vql`, done in T24 — see section 9

---

## 1. Задача

Дать ИИ-агентам возможность создавать объекты в платформе Denodo, описывая намерение
обычным текстом, — без траты токенов на чтение онлайн-документации и поиск примеров VQL.

Целевой сценарий («вайб-кодинг на Denodo»): человек формулирует задачу словами, агент
пишет корректный VQL, применяет его к живому Virtual DataPort, проверяет результат и
оставляет после себя версионируемый скрипт.

Virtual DataPort — основной адресат, но не единственный: Denodo это одна платформа из
нескольких серверов, и часть объектов создаётся не через VQL, а REST-вызовами. Сценарий
от этого не меняется, меняется только канал.

## 2. Ключевое решение: навыки, а не MCP-сервер

Навыки и MCP решают разные задачи и не являются альтернативами:

| | Навыки (skills) | MCP-сервер |
|---|---|---|
| Что даёт | **знание** — как правильно написать VQL для объекта X | **руки** — выполнить, посмотреть каталог, проверить |
| Живёт | в файлах репозитория | в процессе с креденшелами к VDP |
| Стоимость в контексте | ~30 токенов на навык (только `description`), тело читается по требованию | схемы всех инструментов, постоянно |
| Решает исходную задачу | да | нет |

Обоснование выбора:

1. **Progressive disclosure — ровно нужный механизм.** Фронтматтер навыка постоянно
   находится в контексте и стоит копейки; тело `SKILL.md` читается только при
   релевантности, `references/*.md` — только когда нужен конкретный раздел.
2. **У Denodo уже есть официальный MCP-сервер, и он решает другую задачу.** Denodo MCP
   Server и Denodo AI SDK с MCP-режимом сфокусированы на Query RAG: естественный язык →
   `SELECT` по существующим витринам. Это потребление данных, а не разработка объектов.
   Собственный MCP ради DDL дублировал бы транспорт, который у Denodo и так есть, и всё
   равно не дал бы знания VQL.
3. **Исполнение дешевле получить без MCP.** У агента уже есть Bash. Скрипт-обёртка плюс
   навык описывают исполнение без отдельного процесса, конфигурации и постоянного
   налога на контекст.

Собственный MCP-сервер рассматривается заново только при появлении задачи, которую
навык плюс скрипт закрыть не могут — например, семантический поиск по каталогу из
тысяч представлений.

## 3. Вводные и ограничения

| Параметр | Значение |
|---|---|
| Целевая версия Denodo | 9.x, только последняя (latest / 9.5); развилок по версиям нет |
| Что делает агент | генерирует VQL **и применяет** его к живому VDP: выполняет DDL, читает ошибки, итерирует |
| Каналы доступа | Python-клиент к VDP и REST/Management API; список расширяется по мере надобности |
| Аудитория | публичный open-source плагин на GitHub (Claude Code plugin / marketplace) |
| Требования к примерам | никаких клиентских данных, реальных хостов и схем в репозитории |

**Источники истины при разработке шаблонов** — все три одновременно:

1. обязательный прогон на живой платформе;
2. официальная документация Denodo 9.5;
3. реверс из VQL-экспортов реальных проектов, сгенерированных Design Studio (там
   встречаются конструкции, которых по документации не угадать).

## 4. Архитектура: карта навыков

Выбран гибридный подход — общее ядро плюс доменные навыки.

```
/denodo:vql           ядро: рабочий цикл, конвенции, безопасность, идемпотентность
/denodo:execute       применение VQL к живому VDP, разбор ошибок
/denodo:catalog       виртуальные базы, папки, теги VDP
/denodo:datasources   источники, wrappers, base views
/denodo:views         derived views (joins, unions, FLATTEN/NEST), interface views, ассоциации; impact of a change, lineage, delegation
/denodo:marketplace   Data Marketplace: теги, категории, external elements (REST)
/denodo:procedures    хранимые процедуры: предопределённые, VQL, Java (вне v1)
/denodo:cache         full cache of a view: on and off, load, clear (T27, beyond v1)
/denodo:semantics     metadata AI consumers read: descriptions, keys, associations, MCP tag (T28, beyond v1)
/denodo:metrics       metric views: KPIs defined once, the views over them, evaluate_metric (T29, beyond v1)
/denodo:security      who reads what: roles given to users, global security policies over tagged columns (T31, beyond v1)
/denodo:ai            the server's LLM in a query: text functions over rows, their answers cached, semantic search over stored vectors (T32, beyond v1)
/denodo:dml           rows changed through a view: INSERT, UPDATE, DELETE, the generated key back, a view an application writes through, upserts (T33, beyond v1)
/denodo:materialize   query results stored as tables: remote tables and REFRESH, summaries, data movement, materialized tables (T34, beyond v1)
/denodo:testing       regression tests: .denodotest files run by the Denodo Testing Tool, its configuration written from a profile (T35, beyond v1)
/denodo:scheduler     work on a schedule: Denodo Scheduler cache jobs and VDP jobs (one statement, a CSV export), run, enable, disable, reports — REST (T36, beyond v1)
```

The dialect has no skill of its own (section 9): it is a table in the body of `/denodo:vql`
and `vql/references/dialect.md`.

Ядро не является оглавлением: карта навыков занимает в нём последние несколько строк, а
тело составляют правила, которые не растут при добавлении новых доменных навыков.

**The boundary at `AS`:** `views` owns the DDL wrapper (`CREATE VIEW ... FOLDER ... AS`); the
expressions inside it — and in every other `SELECT` — are the dialect table of `vql` and its
`references/dialect.md`.

**Граница `datasources` ↔ `views`:** base view создаётся вместе с источником и wrapper'ом
и потому живёт в `datasources`; `views` отвечает за производные представления.

**Граница `procedures` ↔ `datasources` проходит по задаче, а не по механизму.**
Интроспекция JDBC-источника выполняется предопределёнными процедурами
(`PING_DATA_SOURCE`, `GET_JDBC_DATASOURCE_TABLES`, `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW`),
но это шаг цепочки «источник → wrapper → base view», а не работа с процедурами. Он остаётся
в `datasources`; `procedures` отвечает за вызов процедур как таковой и за написание своих.

**Граница `catalog` ↔ `marketplace` проходит по серверу, а не по слову.** Теги есть и в
Virtual DataPort, и в Data Marketplace, но это разные объекты: первые создаются через VQL,
вторые — через REST, а импортированные в маркетплейс теги VDP доступны там только на
чтение. Навык, перепутавший сторону, выполнит корректный вызов не на том сервере.

## 5. Структура репозитория

Плагинные навыки автоматически получают namespace плагина: `skills/views/` внутри
плагина `denodo` становится `/denodo:views`. Поэтому имена директорий не содержат
префикса `denodo-`.

```
denodo_skills/                        репозиторий = плагин = маркетплейс
├── .claude-plugin/
│   ├── plugin.json                   name: denodo
│   └── marketplace.json              один плагин, source: "./"
├── skills/
│   ├── vql/
│   │   ├── SKILL.md                  includes the table of silent dialect deltas
│   │   └── references/dialect.md     text, numbers, dates, NULL and query shape, JSON, delegation
│   ├── execute/
│   │   ├── SKILL.md
│   │   └── references/errors.md
│   ├── catalog/SKILL.md
│   ├── datasources/
│   │   ├── SKILL.md
│   │   └── references/               jdbc, json, xml, df, excel, odata, s3
│   ├── views/
│   │   ├── SKILL.md
│   │   └── references/               derived, interface, associations, unions, arrays, dependencies, delegation
│   ├── marketplace/
│   │   ├── SKILL.md
│   │   └── references/               tags, categories, external elements
│   ├── procedures/
│   │   ├── SKILL.md
│   │   └── references/               predefined, vql-procedures, java-procedures
│   ├── cache/
│   │   ├── SKILL.md
│   │   └── references/full-cache.md  every load parameter and ALTER VIEW … CACHE form, measured
│   ├── semantics/
│   │   ├── SKILL.md
│   │   └── references/metadata.md    what each AI consumer reads, every metadata ALTER, inheritance
│   ├── metrics/
│   │   ├── SKILL.md
│   │   └── references/metric-views.md  grammar, joins per association measured, query rules, limits
│   ├── security/
│   │   ├── SKILL.md
│   │   └── references/               policies (grammar, masks, audience per grant path), privileges
│   ├── ai/
│   │   ├── SKILL.md
│   │   └── references/               functions (each LLM function as measured), vectors (type, distances, model choice, delegation)
│   ├── dml/
│   │   ├── SKILL.md
│   │   └── references/               statements (grammar, RETURNING, upsert, how values land, transactions), writable-views (per view type, CHECK OPTION, wrapper switches, cache, impersonation)
│   ├── materialize/
│   │   ├── SKILL.md
│   │   └── references/               remote-tables (procedure, command, types, REFRESH, materialized and temporary tables), summaries (grammar, rewrite measured, staleness, data movement)
│   ├── testing/
│   │   ├── SKILL.md
│   │   └── references/format.md      the .denodotest format as the Testing Tool runs it: parsing, comparison rules measured, SETUP/TEARDOWN, exit codes, the configuration
│   └── scheduler/
│       ├── SKILL.md
│       └── references/rest-api.md    the Scheduler calls, every field of a cache job, a VDP job and the CSV exporter with its default, reports, triggers
├── scripts/
│   ├── denodo                        launcher (только stdlib)
│   └── denodo_cli/                   реализация
├── evals/                            фраза → ожидаемый навык
├── README.md
└── LICENSE
```

Репозиторий одновременно является плагином и маркетплейсом, отдельный
репозиторий-каталог не нужен. Маркетплейс называется `denodo-skills`, плагин — `denodo`,
поэтому установка: `/plugin marketplace add kirivandubai/denodo_wipe_coading_skills`,
затем `/plugin install denodo@denodo-skills`. Имя репозитория на GitHub отличается и от
имени маркетплейса, и от имени локальной директории.

Следствие `source: "./"`, проверенное на локальной установке: в кэш плагина
(`~/.claude/plugins/cache/<маркетплейс>/<плагин>/<версия>/`) копируется весь репозиторий,
включая `docs/` и `CLAUDE.md`. На работу навыков это не влияет — они читаются из
`skills/`, — но объём установки растёт вместе с документацией.

**Три следствия из спецификации Claude Code, влияющие на дизайн:**

1. **`${CLAUDE_PLUGIN_ROOT}` подставляется и в теле навыка, и в `allowed-tools`.** Это
   позволяет навыку `execute` объявить
   `allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/denodo *)` — и агент выполняет VQL
   без запроса разрешения на каждый вызов. Снимает основное трение цикла
   «выполнил → упало → чиню».
2. **Содержимое навыка попадает в контекст один раз и не перечитывается** на следующих
   ходах. Навыки пишутся как постоянно действующие правила, а не как одноразовый рецепт.
3. **Бюджет `description` — 1536 символов** в листинге (обрезается совместно с
   `when_to_use`). Хватает и на триггерные фразы, и на строку «не для X — используй Y».

## 6. Ядро `/denodo:vql`

### 6.1 Рабочий цикл

Ключевое правило: **агент пишет VQL в файл проекта, а не выполняет из головы.**

```
намерение текстом
  → определить размещение (база, папка) по конвенциям
  → написать .vql в репозиторий проекта
  → применить через /denodo:execute
  → проверить, что создалось (DESC / пробный SELECT)
  → файл остаётся в git
```

Без этого правила вайб-кодинг порождает объекты, существующие только на стенде и ни в
одном артефакте: их нельзя отревьюить, перенести в другую среду или воспроизвести после
отката.

### 6.2 Конвенции именования и раскладки

Префиксы объектов, слои (подключение → интеграция → бизнес), структура папок. Без них
агент каждую сессию изобретает свою схему, а Denodo-проекты живут годами.

**Источник конвенций: дефолт в ядре плюс переопределение проектом.** В ядре — набор по
умолчанию на основе best practices Denodo. Проект может положить собственный файл
конвенций (по умолчанию `.denodo/conventions.md` в корне проекта), агент читает его и
перекрывает дефолты. Работает из коробки, не навязывая правила командам со своими
стандартами.

**Дефолт взят из официального документа Denodo «VDP Naming Conventions»** (Denodo
Community KB), а не придуман: `ds_`, `bv_`, `iv_`, `a_`, `s_`, бизнес-сущность без
префикса, слои как нумерованные папки `/01 - connectivity`, `/02 - integration`,
`/03 - business entities`, `/06 - associations`, имена в нижнем регистре через
подчёркивание, в единственном числе, без имени среды. Единственное добавление плагина —
`wr_<система>_<сущность>` для wrapper'а: в документе его нет, а в цепочке v1 он есть.

**Формат файла переопределения — обычный markdown, читается целиком.** Раздел файла,
названный по правилу из ядра (имена объектов, папки-слои, база), заменяет это правило;
всё, чего файл не упоминает, остаётся дефолтом ядра. Схемы, ключей и валидации нет
намеренно: файл пишет человек для людей и агента сразу, а частичное переопределение
списком ключей потребовало бы формата, который придётся поддерживать в каждом навыке.
Проверено на живом стенде 9.5.1: имена папок с цифрой, пробелами и дефисом парсер
принимает, путь папки регистронезависим, но родительская папка обязана существовать до
дочерней (`Cannot create folder …: parent not found`) — создаются сверху вниз, удаляются
снизу вверх.

### 6.3 Правила безопасности

`CREATE` нового объекта — агент выполняет сам. `DROP`, `ALTER` существующего объекта и
любое действие в среде с признаком прода — только после явного подтверждения человека.
Для публичного плагина обязательно: его установят на боевые стенды.

**Whose `ALTER` (T32, owner's decision).** "Existing" means existing before this session. An
`ALTER` of an object the agent created in the same session, which nothing it did not create
reads yet — the `ALTER VIEW … CACHE FULL` line in a new view's own file, the second statement
of the `cache` and `ai` templates — is the agent's own change and needs no yes. A `DROP` needs
one whatever it hits, and on a profile marked production every change does. The classifier
still flags every `ALTER`: it sees no ownership, and the flag only refuses on production.

**Who created it: the session ledger and `vql plan` (T39).** "Created in this session" decides
half of the table in `/denodo:vql`, and the agent used to carry the answer in its context — which a
compacted session, a subagent, or an object of the same name on the server defeats: the baseline of
T39 held all six requested changes for the human when it could not tell its views from a colleague's,
and replaced a colleague's view citing "your project's own file declares it" about a file it had just
written. The tool now keeps the answer. Every `vql run` records, per session and per VDP server, the
objects it created — those that did not exist before the statement — with the server's
`internal_id` (`CREATE OR REPLACE` and `RENAME` keep it, `DROP` + `CREATE` changes it: measured on
9.5.1), and follows their drops and renames. `vql plan <file>` reads the file against that ledger and
the live catalog and says per statement `exists`, `own`, `needs_yes`, `why` (the row of the table)
and `conditions` (what the row needs that no catalog shows) — and, when anything waits, `yes`: what
the yes is, a yes to the shown statements, never the request that asked for them (T42: an outcome
scenario's agent took the request for it); `api … --plan` does the same for a REST
call without sending it, and for a catalog `synchronize` checks both `changes` against the ledger.
"Your project's own file declares it" is read from git: the tree of the last commit made before the
session started — a file the session wrote or committed vouches for nothing. **The plan informs and
refuses nothing**; the refusal stays the production profile's (roadmap 2.1). The session is the
conversation with the human, subagents included: `DENODO_SESSION`, else `CLAUDE_CODE_SESSION_ID`
(a subagent sees its parent's id — measured on Claude Code 2.1.289); without either the ledger is
off and only an object an earlier statement of the same input creates counts as the input's own. The
mapping of the table onto statements is in
[the T39 design](2026-10-06-session-ledger-and-plan-design.md).

**Criterion for "destructive" (T22, owner review of the roadmap, item 2.1).** A statement is
destructive when it destroys or overwrites something that exists, or changes state outside
the agent's own project: server settings, data in sources, objects of other databases, global
objects. `CREATE` of a new object in the agent's own database is not. A text classifier sees
no ownership, so every `DROP` and `ALTER` stays destructive whatever it hits. The classifier is
a deny list and never complete; the rule for growing it: a skill that teaches a
state-changing statement or procedure extends the classifier in the same PR — both copies of
the procedure list in one change.

**By leading keyword** the tool flags `DROP`, `ALTER` (`drop`, `alter`), `DELETE`, `TRUNCATE`
(`delete`), `INSERT`, `UPDATE` (`write`: a write through a view lands in the source; VQL 9.5
has no `MERGE` — the 9.5.1 parser rejects it — and its merge form is
`INSERT … ON DUPLICATE KEY UPDATE`), the server-wide `SET '<property>' = …` and `WEBCONTAINER`
(`setting`: `SET` with a quoted property rewrites `VDBConfiguration.properties` and propagates
to servers sharing an external metadata database; `= NULL` deletes the property). Session
settings pass on any profile: the ODBC connection form `SET <property> TO …` (unquoted — an
allow-listed shape, every other `SET` counts as the server), `ALTER SESSION SET …` (checked on
9.5.1: the value shows in `GETSESSION` on the same connection and is gone on the next one), and
`WEBCONTAINER STATUS`.

**By CONTEXT (T27)**, a query that writes the cache of a view instead of reading it is flagged
`cache`: `'cache_invalidate'` in any form (it deletes cached rows before the load — all of them
with `'all_rows'`), and `'cache_preload' = 'true'` without it (it appends to what is cached, so
a second run doubles every row). The statement starts with `SELECT`, so neither the keyword
nor the procedure check sees it. `'cache' = 'off'`, the read that bypasses the cache, is not a
write. `ALTER VIEW … CACHE …` is already `alter`.

**By statement (T31)**, `CREATE [OR REPLACE]` of a `USER`, a `ROLE` or a
`GLOBAL_SECURITY_POLICY`, `CHOWN`, and a `CREATE DATABASE` that carries a `GRANT` or `REVOKE`
clause are flagged `security`. They start with `CREATE`, which is otherwise a clean create,
but each changes who may read what across the server; and `CREATE OR REPLACE` of an existing
role or user keeps every grant and role it had and adds the new ones (checked on 9.5.1), so
it is never the "new object" the keyword suggests. `ALTER USER | ROLE | DATABASE` and
`ALTER GLOBAL_SECURITY_POLICIES` are already `alter`. A tag assignment that brings a column
under an existing policy is a security change no text classifier can see: the rule for it
lives in the skill.

**Tables in source databases (T34, owner's decision on roadmap 9.2, part 3).** `CREATE [OR
REPLACE] REMOTE TABLE` and `CREATE [OR REPLACE] SUMMARY VIEW` create a table in a source database
and load it, `OR REPLACE` dropping whatever table had the name; `REFRESH` empties a remote table
or a summary and loads it again; `CREATE OR REPLACE MATERIALIZED TABLE` over one with rows
leaves it empty (checked on 9.5.1). All four are flagged `table`; a plain `CREATE MATERIALIZED
TABLE` and `SELECT … INTO` refuse a name that exists and pass. The rule the skill teaches is the
owner's: a **new** table, by a statement that cannot overwrite one (`CREATE_REMOTE_TABLE` with
`replace_remote_table_if_exist = false`), in the data source and schema the human named, under a
name checked free, is the agent's own, and so is a `REFRESH` or a replacement of that table in
the same session — and an `INSERT` or an upsert into it, an incremental load (T43: it changes less
than the `REFRESH` the rule already gave; `vql plan` says so for a remote table and a materialized
table the ledger records — not an `UPDATE` or `DELETE` of it, nor a load whose query calls an AI
function over rows); replacing, emptying or dropping a table older than the session waits for the
yes, and so does every load of a summary, because from then on the optimizer answers other
people's queries from it. A summary created with `DATA_LOAD_IMMEDIATE = FALSE` changes no
answer and is the agent's; data movement added to a view older than the session is the yes —
every query of it then creates a table in the target database. The classifier still flags the
new table: on a production profile every change waits for the yes.

**Для HTTP-канала правило формулируется по методу и пути, а не по глаголу.** `DELETE`
тега, категории (каскадно с потомками) и external tool server (со всеми его элементами)
— тот же `DROP`; но разрушительны и некоторые `POST`: `tags/vdp/synchronize` с неполным
списком стирает остальные импортированные теги, синхронизация каталога с
`proceedWithConflicts:"SERVER"` затирает локальные правки, `external-tool-servers/synchronize`
удаляет элементы, исчезнувшие из снимка интерфейсного представления, а `views/{id}/tags` и
`category-management/views/{id}/categories` заменяют набор назначений представления, а не
дополняют его. Перечень — раздел 6 [отчёта T11](2026-09-08-spike-t11-marketplace-api.md),
уточнённый в T8d по OpenAPI живого сервера 9.5.1: разрушительна не только форма
`element-management/all/synchronize`, но и `element-management/{DATABASES|VIEWS|WEBSERVICES|
EXTERNAL_ELEMENTS}/synchronize`, а пути `views/{id}/categories` в API вовсе нет — «сет»-вызов
для категорий живёт под `category-management/`.

**When the agent synchronises the marketplace catalog itself (owner's decision, 2026-10-05).**
`DATABASES/synchronize` and `VIEWS/synchronize` stay destructive in the classifier, but the
agent runs them without a yes — with `proceedWithConflicts: "SERVER_WITH_LOCAL_CHANGES"`, never
on a production profile — when both `…/changes`, read right before the call, hold only the
session's own objects: every `localElements` entry is the element of a view the session created
(its own renamed view, with the pair matched in the call, included), and every `serverElements`
entry is a database or view the session created. `modifiedElements` do not change this: that
mode keeps every description edited in the marketplace. After the call the agent reads
`removed` and `inserted` against the radius it read, and both `changes` again — once a database
is gone from VDP, its elements leave the catalog with `removed` empty (T37, measured on 9.5.1) —
and tells the human at once about anything else. Any other radius waits for the yes. Renaming a view that existed before the session: one
yes covers the `ALTER … RENAME` and the `synchronize` with the pair matched, when both are shown
together. The first import on an external tool server created in the same session stays the
other exception. The rule is the same as "your own new — yourself" for tables (T34): the call
changes nothing in the shared catalog that the session did not make.

**The Scheduler's HTTP rule (T36).** On the Scheduler (`api --server scheduler`) every `PUT`
replaces the whole object it names — a job, a project, a data source — and is `alter`; a
job's `status` change (start, stop, enable, disable) is `job`; every `DELETE` and report
deletion is `delete`; configuration, roles, passwords and a metadata import are `setting`,
`security` and `replace`. A new job is classified by what it will run on every trigger with
nobody watching — a cache job `cache`, a VDP job the kind of its VQL statement (`REFRESH` →
`table`, `DROP` → `drop`), any exporter `write` (a table, an index, or a file each run
overwrites) — the one place the
classifier reads a body, because there the body is the operation. The rule the skill teaches:
**a job is its statement, run every time it fires.** Creating a job disabled changes nothing
and is the agent's — it is how the server shows the job before anyone agrees to it; enabling it
needs whatever running its statement now would need (a reload of a cache somebody reads, a
`REFRESH` of an older table, a write over a file not created in the session), and so does a
start; anything on a job that existed before the session is the human's. A job whose runs
touch only what the agent created in the session is the agent's, enabled and run. The marker
on a production profile is the same as everywhere: every change waits.

**Для VQL правило дополняется именем вызываемой процедуры.** Предопределённые процедуры,
меняющие состояние, вызываются как чтение — `SELECT … FROM DROP_REMOTE_TABLE(…)`,
`CALL CLEAN_CACHE_DATABASE(…)` — и по первому ключевому слову не ловятся. Инструмент
(T20) сверяет имя процедуры в `SELECT … FROM <имя>(` и `CALL <имя>(` с чёрным списком
из процедур (nine in T20; T37 added `COMPACT_CACHE`, `REFRESH_BASE_VIEW`, `CREATE_TAGS_FROM_VIEW`,
`CREATE_TAGS_FROM_COLLIBRA`, `LOGCONTROLLER`, `GENERATE_STATS_FOR_FIELDS`,
`GENERATE_SMART_STATS_FOR_FIELDS`, `COMPUTE_SOURCE_TABLE_STATS`, `MAINTAIN_METADATA_TABLES` — each
changes state and was named by a skill without being on the list): `GENERATE_STATS`, `CREATE_REMOTE_TABLE`, `DROP_REMOTE_TABLE`,
`CLEAN_CACHE_DATABASE`, `DROP_NONACTIVE_CACHE_TABLES`, `CREATE_SCHEMA_ON_SOURCE`,
`DROP_SCHEMA_ON_SOURCE`, `REMOVE_ICEBERG_VIEW_SNAPSHOTS`, `ROLLBACK_ICEBERG_VIEW_TO_SNAPSHOT`
— и помечает вызов `destructive: "procedure"`. Именно чёрный
список, а не белый: `GET_ELEMENTS()`, `DUAL()` и остальная сотня читающих процедур должны
проходить. Список ведётся в двух местах намеренно — в коде (`scripts/denodo_cli/safety.py`,
инструмент не читает файлы навыков во время работы) и в навыке
(`skills/procedures/references/predefined.md`, навык самодостаточен) — и юнит-тест
`tests/test_safety.py` падает при расхождении копий. Граница: пользовательская VQL-процедура,
делающая DDL через `EXECUTE` внутри себя, по имени не ловится; правило «прочитать, что
делает процедура, прежде чем вызывать» остаётся у ядра.

### 6.4 Идемпотентность

Правила написания VQL, переживающего повторное применение.

**Дефолт — `CREATE OR REPLACE`.** По документации 9.5 его поддерживают все двенадцать
VQL-объектов v1: `DATABASE`, `FOLDER`, `TAG`, `DATASOURCE` (JDBC, DF, JSON), `WRAPPER`
(JDBC, DF, JSON), `TABLE`, `VIEW`, `INTERFACE VIEW`, `ASSOCIATION`. Развилок по типам
объектов в шаблонах нет.

**Подтверждено на стенде 9.5.1 (спайк T2, [отчёт](2026-09-08-spike-t2-ddl-over-9996.md)):** `CREATE OR REPLACE`
повторно применяется поверх существующих объектов девяти проверенных типов без ошибок и
без разрушения цепочки; `DROP ... IF EXISTS` работает для всех этих типов, а не только
для тега, и молчит по уже удалённому объекту. Не прогонялись только JDBC- и
JSON-варианты источников и wrapper'ов — их закроет T12.

Две оговорки из того же спайка: `DROP FOLDER IF EXISTS` не спасает от папки с
содержимым — удалять снизу вверх; а назначение тега через `ADD_TO` требует парного
блока `REMOVE_FROM`, иначе это синтаксическая ошибка (раздел 4.1 отчёта).

**Проверено при работе над T6 на стенде 9.5.1 (2026-09-09), потому что дефолт без этого
обходят:** `CREATE OR REPLACE DATABASE` поверх непустой базы **сохраняет её содержимое** —
представления и папки остаются на месте. Базовый прогон показал, что агент без ядра
предполагает обратное и выносит `CREATE DATABASE` в отдельный «bootstrap»-файл, ломая
правило «один файл, применяемый целиком». Альтернативы у дефолта нет: `IF NOT EXISTS` в
Denodo не существует — `CREATE DATABASE IF NOT EXISTS` даёт
`Syntax error: Exception parsing query near 'IF'`. Дополнительно: `CREATE OR REPLACE VIEW`
поверх звена цепочки не ломает зависимые представления, если изменение аддитивно.

Для объектов маркетплейса идемпотентность обеспечивается не синтаксисом, а порядком
вызовов: перед созданием — поиск по имени. Подтверждено T11: все операции идут по
числовым `id`, дубликат имени — `409`, а статус повторного `DELETE` у разных объектов
разный (`500`, `200`, `404`), так что опираться можно только на предварительный поиск.

### 6.5 Many objects at once (T41)

A request that names a set — every table of a schema, every column that holds an email, every
view of a database — is the most frequent ask the review of all skills found uncovered
([review](2026-10-05-skills-review.md), recommendations). It gets no skill of its own: the core
`vql` carries one pattern, and the domain skills apply it where their objects come in sets.

**The pattern** (`vql`, *Many objects at once*): the list comes from the server, whole, in one
read (`--max-rows`, and `truncated` checked — the tool keeps 100 rows by default); a plan file
beside the statements, `<change>.plan.md`, with one row per candidate and the decision in the row
— what it comes from, the action or why none, whose it is, the file that carries it, a status;
the statements generated from the list into one file per yes — what is the agent's in the file it
applies, what waits in a file of its own, and, when the human has to read every object (texts,
tags on views of others), batches of tens of objects, a file and a yes each; the apply as always;
a check of every object — a catalog read compared with the list row for row, and for rows a file
of reads, one statement per view, run with `--continue-on-error` — whose result goes into the
plan's status column. The message names the plan file, the counts per status and every row that
is not done; the yes covers each file as it was shown.

**Why a file, not the message.** The baselines of T41 (23 tables, 21 views, 26 views) kept the
safety rules — the session ledger and `vql plan` of T39 told them whose each object was — and
failed on the list instead: a tag on eleven of the agent's own views put on with one `ADD_TO`
outside their files, gone at the next apply; inventories cut at the tool's row limit; one
generator call per table; and no artifact that says, per object, what happened. The plan file is
that artifact, and the human's one yes is to the files it names.

**What the tool adds.** `vql plan` reports `actions` (statements counted by what they do) and
`duplicates` — two statements of one input declaring one object, the later silently replacing the
earlier, which is what a naming rule that maps two tables to one name produces in a generated
file. `vql run --continue-on-error` gets its second sanctioned use, a file of reads that checks
many objects. Nothing refuses: the plan still informs only (roadmap 2.1).

**Where each domain applies it.**

- `datasources` (`references/jdbc.md`, *Every table of a schema*): what already has a base view,
  by the table it reads (`GET_ELEMENTS` joined with `GET_SOURCE_TABLE`, JDBC base views only — one
  of another kind fails the whole query); every wrapper and base view in one query
  (`GET_JDBC_DATASOURCE_TABLES` joined with `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW`, the name an
  expression, the wrapper renamed by `REPLACE`, constant inputs in `WHERE` — in `ON` they fail);
  the generator's first row, `CREATE OR REPLACE FOLDER` without a description, left out — it
  clears the folder's description, and over a folder older than the session it is a yes.
- `catalog` (*One tag on many columns*) and `security`: the list by name and by lineage
  (`GET_ELEMENTS` joined with `COLUMN_DEPENDENCIES`); a tag on a view with a file goes into the
  file — a view over a `UNION` refuses field properties, so its file carries an `ALTER TAG` right
  after the view; the check is `GET_VIEW_TAGS` against the list.
- `semantics` (*A database of many views: batches*): every view still profiled, batches of what
  the human reads, base views first because their field texts are inherited upward.

## 7. Слой исполнения `/denodo:execute`

### 7.1 Транспорт

Используется **официальный `denodo-sqlalchemy`** — диалект Denodo для SQLAlchemy. Он же
даёт вторую точку расширения: тот же диалект поддерживает `denodo+psycopg2` (порт 9996)
и `denodo+flightsql` (порт 9994, VDP 9.1+). Переключение — строкой в профиле среды, без
правки кода.

### 7.2 Установку выполняет скрипт, а не человек

```
scripts/denodo          launcher, только stdlib — не падает никогда
   │
   ├─ есть uv?          → uv run с inline-зависимостями (PEP 723)
   ├─ иначе             → venv в ${CLAUDE_PLUGIN_DATA}, пакеты ставятся один раз
   └─ не вышло          → одна строка с точной командой установки
```

`${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/denodo/`) — персистентная директория
плагина, переживающая его обновления: venv создаётся при первом запуске и дальше
переиспользуется. Пользователь ничего не устанавливает руками, при этом клиент остаётся
официально поддерживаемым.

Launcher обязан быть на голой стандартной библиотеке — иначе упадёт раньше, чем успеет
настроить окружение.

### 7.3 Расширяемость

Часть функциональности (Data Marketplace, каталог) через VQL недоступна, поэтому
транспорты живут за общим интерфейсом:

```
denodo_cli/
  transports/
    vql_psycopg2.py     denodo+psycopg2, порт 9996        (по умолчанию)
    vql_flightsql.py    denodo+flightsql, порт 9994       (VDP 9.1+)
    api_rest.py         REST: Data Marketplace, the Scheduler (T36)   (то, чего нет в VQL)
```

Единый контракт `execute(vql) -> rows | error`. Новый транспорт — это один файл и строка
в профиле среды, а не правка навыков.

Набор команд, реализованный в T5 (`scripts/denodo --help`):

```
scripts/denodo vql run   --env dev model/sales/views.vql     файл, '-' (stdin) или -e "VQL"
scripts/denodo vql desc  --env dev bv_orders [--vql] [--type "datasource df"]
scripts/denodo api get   --env dev /public/api/tags/count   [--param k=v] [--json …] [--part …]
scripts/denodo api --server scheduler get --env dev /public/api/projects   the Scheduler's REST API (T36)
scripts/denodo env list | check --env dev | init            профили; init — интерактивно
scripts/denodo secret encrypt --env dev       пароль источника со stdin → шифр (T15)
scripts/denodo testing run --env dev --database sales_analytics --tool <dir> tests/   the Denodo Testing Tool on a folder of tests (T35)
scripts/denodo testing config --env dev --database sales_analytics   configuration.properties of the Testing Tool from the profile (T35)
scripts/denodo verify    --env dev            прогон шаблонов, см. раздел 11.1 (появится в T12)
```

Поведение, зафиксированное T5:

- **Файл режется на выражения клиентом** (по `;` вне строк и комментариев) и исполняется
  по одному в одной сессии; при ошибке — остановка, в ответе индекс и текст упавшего
  выражения (`--continue-on-error` исполняет остальные). Проверено на стенде: если
  отправить серверу несколько выражений одной строкой, он выполняет всё до ошибки и
  ничего после неё, без отката, — так что клиентское разбиение ничего не меняет в
  семантике, но даёт точную диагностику. `CONNECT DATABASE` в файле работает, потому что
  сессия одна на весь прогон.
- **Разрушительные операции помечаются в ответе** (`destructive: drop|alter|delete|write|setting|procedure|cache|security|table|job`
  для VQL — по ключевому слову и по имени вызванной процедуры, and by `CONTEXT` for a cache write (T27), and by the security statement (T31); `delete|replace` для HTTP —
  по методу и пути, раздел 6.3; on the Scheduler also `alter`, `job` and the kind of a new job's statement, T36) и на профиле с
  `production = true` отклоняются до исполнения без флага `--allow-destructive`. Само
  подтверждение человеком остаётся правилом ядра: флаг лишь не даёт выполнить такое молча.
- **Коды выхода:** `0` — успех, `1` — сервер отказал, `2` — ошибка вызова, конфигурации или
  отклонённая разрушительная операция, `3` — не поднято окружение. Ответ всегда один
  JSON-документ на stdout с полями `ok`, `command`, `env {name, production, transport,
  database}`; у ошибок — `error {kind, message}`, у HTTP — `status` отдельно от `body`.
- **A write reports what it changed (T33).** An `INSERT`, `UPDATE` or `DELETE` returns no
  result set, so a `vql run` entry carried nothing to tell one row from a whole table. Every
  entry now has `affected`: the count the server reports for the statement through the
  driver's `rowcount` — measured on 9.5.1 to match the rows changed, `0` when nothing matched —
  and `null` for a read, DDL (the driver says `-1`) or a failed statement. It is the only number
  a preview can be compared with.
- **`env check` says who the profile's user is (T31, roadmap 2.5).** `vdp.admin` is
  `adminglobal` from `DESC USER <user>`, which any user may run on themselves: global security
  policies and restrictions never apply to an administrator, so their own `SELECT` proves
  nothing about a policy. `vdp.impersonation` is whether a query may run as someone else
  (`CONTEXT ('impersonate_user' = …)`), asked by impersonating the profile's own user over
  `Dual()`; the server refuses a user without the `impersonator` role in words of its own.
  Both are `null` when the server does not say (a user known only to LDAP or an identity
  provider, or another refusal). This replaces the second, non-administrator profile the
  roadmap asked for (decision 9.3): impersonation checks a policy as each user or role
  without a password, where a second profile needs one per user and checks only that one.
- **The Scheduler is the second REST server (T36).** `api --server scheduler` sends the call to
  the Scheduler administration tool with the profile's account (HTTP Basic) and adds the `uri`
  query parameter naming the Scheduler server unless the call gives one, as the marketplace
  transport adds `serverId`. The profile may name both (`scheduler_url`, `scheduler_uri`);
  without them the address is the origin of `marketplace_url` (or `http://<host>:9090`) plus
  `/webadmin/denodo-scheduler-admin` and the server `//<host>:8000` — the administration tool is
  a web application of the same web container, so an existing profile needs no edit, and older
  copies of the tool, which reject an unknown field, keep working. `env check` reports
  `scheduler` (version, mode, the user's Scheduler roles) where the profile names a web
  container; an installation without a Scheduler does not fail the check. The baseline runs of
  T36 had no channel: one loaded the profile's password through the plugin's own loader into a
  helper, four tried `api get ../webadmin/…` to carry the marketplace's account to the
  Scheduler. `api` now refuses a path with a `..` segment on either server.

### 7.4 Правила

- **Креденшелы только через профиль среды и окружение, никогда в аргументах команды** —
  пароль в аргументе `Bash` оседает в транскрипте сессии. В команде фигурирует лишь имя
  профиля. Пароль **источника** профилем не покрыт: он нужен один раз, чтобы получить шифр
  для `USERPASSWORD … ENCRYPTED`. Для него — `secret encrypt` (T15): пароль читается со
  stdin (в терминале — скрытым промптом `getpass`, иначе пайпом), в ответе только поле
  `encrypted`. Команда не идёт через `run_statements`, который кладёт текст выражения и в
  результат, и в ошибку, а сообщение сервера перед печатью очищается от пароля — иначе
  ошибка вида «syntax error near …» вернула бы плейнтекст в транскрипт.
- **Профили сред лежат вне репозитория проекта** — по умолчанию `~/.denodo/profiles.toml`,
  другой путь — переменной `DENODO_PROFILES`. Так креденшелы не попадают в git ни случайно,
  ни намеренно. Формат зафиксирован в T5:

  ```toml
  [dev]
  host = "localhost"          # VDP
  port = 9996                 # по умолчанию 9996
  database = "admin"          # по умолчанию admin; --database переопределяет на вызов
  user = "…"
  password = "…"              # или password_env = "DENODO_DEV_PASSWORD"
  production = false
  transport = "vql_psycopg2"  # по умолчанию; vql_flightsql заложен, но не в v1
  marketplace_url = "http://localhost:9090/denodo-data-catalog"   # без него `api` недоступна
  # scheduler_url = "http://localhost:9090/webadmin/denodo-scheduler-admin"   # T36; default: the web container of marketplace_url
  # scheduler_uri = "//localhost:8000"                                         # T36; the Scheduler server as the admin tool reaches it
  # marketplace_server_id = 1                                      # обязателен при нескольких VDP
  # jdbc_port = 9999                                               # only for `testing config` (T35)
  ```

  Профиль создаётся командой `scripts/denodo env init` — она интерактивна, пароль
  вводится скрыто, и запускать её должен человек (в Claude Code — `! scripts/denodo env
  init`), а не агент: так пароль не попадает в транскрипт. Имя профиля можно задать
  переменной `DENODO_ENV` вместо `--env`.
- **The Denodo Testing Tool's configuration is written from the profile, not by hand (T35,
  the decision the roadmap left to the task).** The tool reads its JDBC credentials from a
  `configuration.properties` — plain or Jasypt `ENC(…)`, no environment substitution (read in
  its sources). Every baseline run without a sanctioned way to make that file went around a
  rule: two loaded the profile's password through the plugin's own loader into a wrapper
  script, two ran with a password committed to the repository, one could not run its tests at
  all. `testing config --env <p> --database <db>` writes the file from the profile beside the
  profiles file (`<dir>/testing/<env>/<db>.properties`, 0600 in a 0700 directory), answers with
  the path, URL and user and never the password, refuses a path inside a git work tree unless
  the repository ignores it, refuses a password of the form `ENC(…)` (the tool would try to
  decrypt it), and on a production profile refuses without `--allow-destructive` — the tool
  runs a suite's `SETUP`/`TEARDOWN` past the classifier, so the yes has to come before the
  channel exists. The JDBC port is the profile's `jdbc_port`, 9999 by default; the transports
  use `port`. **The agent runs the tests with `testing run`**, which writes the same file into
  a temporary directory for one run, starts the tool's launcher from its `bin/` and answers with
  the exit code, the summary and each test. It is a launcher, not a runner: the tool parses and
  compares, as the owner decided. It was added after a GREEN run: the session's permission
  layer refused a launcher command that named the file under `~/.denodo/` ("Credential
  Exploration") — any path to a file holding a password is at risk of that — and three runs
  lost the tool's exit code in a pipe. `testing config` stays for a human who runs the tool by
  hand. CI writes its own file from its secret store with the same keys.
- **The session's ledger lives beside the profiles (T39)**: `<profiles dir>/sessions/<session>.json`,
  `0600` in a `0700` directory, written under a lock and replaced atomically, deleted after 30 days
  without a write — outside every repository like the profiles. It holds object names and ids, no
  secrets. Keeping it never fails a command: a read or a write that fails leaves the object unrecorded
  and says so in the `ledger` part of the answer.
- **Профиль среды несёт флаг `production: true`** — иначе правило безопасности из ядра
  не имеет опоры: агент должен знать, куда подключён, до выполнения. Каждый ответ
  `scripts/denodo` повторяет этот флаг в поле `env.production`.
- Короткие команды чисто ложатся в предодобрение через `allowed-tools`.
- Вывод машинночитаемый, чтобы агент не разбирал сплошной текст.
- Ошибки Denodo — в `references/errors.md`: что пришло → что означает на самом деле →
  что чинить. Два класса (T7): у VDP кодов нет, только текст, справочник строится по
  подстрокам `statements[failed_at].error.message`; у маркетплейса — HTTP-статус плюс
  `body.code`, когда тело есть. Читается в момент неудачной итерации и окупается быстрее
  прочих файлов.

## 8. Формат доменного навыка

Единый скелет для `catalog`, `datasources`, `views`, `marketplace` — пять блоков в
фиксированном порядке:

```
1. Развилка            «это про X; если тебе нужен Y — /denodo:Y»   (3–5 строк)
2. Минимальный шаблон  рабочий вызов сразу, без предисловий
3. Что нужно выяснить  чего не хватает для заполнения шаблона
4. Куда идти дальше    ссылки на references для нестандартных случаев
5. Проверка            как убедиться, что объект создан правильно
```

**Шаблон не обязан быть VQL.** Часть платформы живёт вне Virtual DataPort: Data
Marketplace управляется REST-вызовами, и тем же способом добавлен Scheduler (T36) и добавится Solution
Manager. Поэтому «минимальный шаблон» — это минимальный рабочий вызов в том канале,
которому принадлежит объект: строка VQL либо запрос через `scripts/denodo api`. Остальные
четыре блока и статус верификации от канала не зависят. Формат описан через каналы, а не
через VQL, чтобы следующий сервер платформы не потребовал переписывать навыки.

**Блок 3 отличает рабочую процедуру от справочника** и критичен для вайб-кодинга. На
фразе «подключи оракл» агенту не хватает хоста, порта, схемы и учётной записи. Навык
явно разделяет: что берётся из профиля среды, что из конвенций, что нужно спросить у
человека. Иначе агент либо выдумает значения, либо устроит допрос из десяти вопросов.

**Порядок и зависимости — тоже в навыке.** Цепочку `datasource → wrapper → base view`
агент должен знать до начала работы.

**Два уровня детализации:** минимальный рабочий шаблон в `SKILL.md`, полный набор опций
с пометками о том, что генерирует Design Studio, — в `references/`.

A reference holds grammar only for what its skill has the agent build (T23): `datasources`
sends every source type beyond its three templates to Design Studio, and its references stop
at those three (roadmap, section 4.4).

**Каждый шаблон несёт статус верификации:**

```sql
-- verified: 9.5 (live, 2026-09-15)
CREATE DATASOURCE JDBC ...

-- unverified: 9.5 documentation only
CREATE DATASOURCE JDBC ... WITH SOME_EXOTIC_OPTION ...
```

У HTTP-шаблона пометка та же и стоит там же — первой строкой, комментарием того формата,
который принят в канале.

**Шаблон может быть цепочкой в обоих каналах.** External element Data Marketplace
(спайк T11) — это цепочка HTTP-вызовов и VQL-фрагмента: тип провайдера, custom external
tool server, затем interface view в VDP по контракту, который выдаёт сам маркетплейс, и
синхронизация. Собственный тип элемента — необязательный шаг: в 9.5.1 их двадцать четыре
встроенных, и чаще подходит готовый (T8d, стенд). Цепочке предшествует синхронизация
каталога маркетплейса с VDP: без неё представление, на которое ссылается ассоциация, не
имеет в маркетплейсе идентификатора, и импорт отказывает целиком. Блок 2 такого навыка —
вся цепочка в порядке выполнения, пометка `verified:` относится к цепочке целиком, а не к
каждому вызову по отдельности.
Это не отменяет правила «один канал на объект»: канал у external element — REST, VQL
там лишь поставляет данные для импорта.

Непроверенный шаблон всё равно предоставляется, но помечается — агент действует
осторожнее и внимательнее проверяет результат. Заодно это даёт честный трекинг
прогресса.

## 9. The SQL dialect: a reference in `vql`, not a skill

**Decided in the roadmap review (2026-09-29), built in T24.** A skill fires on the user's
phrase, and nobody says "mind the VQL dialect": the user asks for a mart or a number, and a
separate `query` skill would load only through a cross-reference while its `description`
competed with `views`. So the dialect is `vql/references/dialect.md` — every row checked on
the server — plus a short table of the deltas that return a wrong value or `NULL` without an
error, in the body of `vql`, which fires on questions about expressions (eval case
`routing-vql-expression`). The reasoning below, written for a separate skill, still holds for
the content — a delta from standard SQL, not a function reference — and no longer for the
form.

**Отдельный навык, не в ядре и не внутри `views`:**

- *не в ядре* — ядро читается почти всегда и должно оставаться маленьким, а справочник
  по диалекту самый объёмный материал набора;
- *не в `views`* — диалект нужен и вне создания объектов: посмотреть данные, отладить
  выражение, проверить гипотезу;
- он **ортогонален классам объектов**: выражения используются в derived views, в
  row/column restrictions, в summary views, в условиях кэша.

**Принцип содержания: не справочник, а дельта от стандартного SQL.** Пересказывать
полный список функций бессмысленно — значительную часть стандартного SQL модель знает.
Ценность в том, где Denodo отличается от того, что модель угадает по привычке из
Postgres или Oracle: там агент ошибается уверенно и молча, пишет правдоподобное имя
функции, которого в VQL нет, и узнаёт об этом только от сервера.

Состав дельты: функции с другими именами (прежде всего даты и строки), типы Denodo и
правила приведения, работа с вложенными структурами, `CONTEXT (...)`, делегирование в
источник и диагностика pushdown.

**Объём в v1: минимальная дельта.** SELECT достаточно просто написать и по документации;
приоритет v1 — сценарий создания объектов. Объём пересматривается позже.

## 10. Срабатывание навыков без явного указания

До чтения навыка модель видит **только `description`**, содержимое `SKILL.md` в этот
момент недоступно. Значит выбор навыка целиком определяется качеством описаний,
написанных под реальные формулировки задач, а не под терминологию документации.

**Пример проблемы — слово «вью».** В Denodo оно перегружено: base view (обёртка над
таблицей источника через wrapper), derived view (`CREATE VIEW ... AS SELECT`), interface
view (контракт без реализации), materialized/summary view (про производительность). Пути
создания принципиально разные.

**Принятая трактовка:** «создай вью» по умолчанию означает **derived view** — base views
создаются пачкой при подключении источника, а не поштучно. `/denodo:views` ведёт в
derived, а его `SKILL.md` начинается с короткой развилки на `/denodo:datasources`.

**Три приёма:**

1. **В `description` — глаголы задачи и VQL-команды, а не название сущности**, плюс
   явное отрицание:

   ```yaml
   # skills/views/SKILL.md
   description: Использовать при создании или изменении представлений в Denodo —
     derived views (selection, join, union, minus, intersection, flatten),
     interface views, CREATE VIEW ... AS SELECT. Также когда пользователь говорит
     "создай вью", "сделай витрину", "собери джойн" в контексте Denodo.
     Не для base views поверх источника — это /denodo:datasources.
   ```

   Строка «не для X — используй Y» работает лучше, чем попытка идеально описать границу.

2. **Ядро `/denodo:vql` как страховочная сеть** — нарочно широкий триггер («любая работа
   с Denodo или VQL»). При неоднозначной формулировке агент попадает в ядро, а ядро
   содержит карту навыков. Цена промаха — одно лишнее чтение небольшого файла вместо
   VQL, сгенерированного по памяти.

3. **Непересекающиеся словари в описаниях.** Если слово встречается в двух
   `description`, одно из них переписывается.

## 11. Верификация

Две независимые проверки, ловящие разные поломки.

### 11.1 Верификация шаблонов: работают ли они

Отдельная тестовая база на стенде (`denodo_skills_test`), команда
`scripts/denodo verify` прогоняет шаблоны и убирает за собой. Результат прогона
обновляет пометки `verified:` в файлах — по явному флагу, см. ниже.

**Синтаксис источников проверяется без самих источников.** `CREATE DATASOURCE JDBC` с
заведомо недоступным хостом всё равно проходит парсер Denodo — ошибка возникает на
подключении, а не на разборе DDL. Значит корректность синтаксиса для Oracle, S3,
Salesforce подтверждается без наличия этих систем. Реальные источники нужны только для
проверки интроспекции и маппинга типов; такие шаблоны помечаются отдельно.

**HTTP-шаблоны проверяются иначе.** Парсера, который подтвердил бы корректность вызова
без его выполнения, у них нет: единственная проверка — реальный запрос к запущенному Data
Marketplace с последующей уборкой созданного. Поэтому marketplace-шаблоны остаются
`unverified` до тех пор, пока на стенде не поднят маркетплейс.

**Прогон — сквозная цепочка, а не набор независимых кейсов.** Шаблоны связаны между
собой: производное представление опирается на базовые, те — на wrapper и источник, тот —
на базу и папку. Поштучный прогон проверял бы каждый шаблон в вакууме и пропускал бы
ровно то, что ломается на практике, — стык между навыками. Поэтому `verify` исполняет
один сценарий в порядке зависимостей: база → папки → файловый источник → wrapper →
базовое представление → производное → интерфейсное → ассоциация → процедуры, и по флагу
хвост маркетплейса.

**План цепочки — в манифесте, механика — в коде.** `verification/chain.toml` описывает
только что и в каком порядке исполняется; фазы, правила безопасности, отчёт и уборка
живут в `denodo_cli/commands/verify.py`. Обратное — интерпретатор поверх декларативного
манифеста — завело бы в репозитории мини-язык, который пришлось бы документировать и
тестировать наравне с кодом.

**Шаг ссылается на блок навыка, а не копирует его.** Адрес — файл, заголовок раздела и
номер блока внутри раздела: `skills/views/SKILL.md#Derived view`. Копия шаблона в
репозитории разошлась бы с навыком молча, и `verify` остался бы зелёным на сломанном
шаблоне; битый адрес, наоборот, роняет прогон.

**Стенд-специфика — подстановкой точных строк.** Тексты навыков остаются цельными
примерами, которые агент копирует буквально, а прогон подменяет в теле блока имя базы
(`sales_analytics`), путь к файлу и имена создаваемых объектов. Подстановка, не
нашедшаяся в теле блока, — ошибка шага: иначе прогон молча ушёл бы писать в чужую базу.

**`serverId` маркетплейса подстановкой не берётся — он приходит из профиля.** Шаблоны
маркетплейса не называют VDP-сервер вовсе, и транспорт добавляет `marketplace_server_id`
сам (раздел 7.4, профиль). Обратное — явное значение в шаблоне и подстановка манифеста поверх
него — механизм профиля выключало: транспорт подставляет, только если вызов сервер не
назвал, а значит форк, проверяющийся на своём маркетплейсе, не мог бы указать свой
сервер иначе, чем правкой этого репозитория (T16).

**Шагов два вида, и отчёт их различает.** `template` — тело из навыка, он и есть предмет
проверки. `fixture` — тело в манифесте: цепочка шаблонов не смыкается сама, навык `views`
опирается на базовые представления, которых не создаёт ни один шаблон, и фикстура готовит
их над демо-данными стенда. Фикстура ничего не верифицирует и пометок не двигает. (Since T40
the fixtures read the chain's own synthetic files, `verification/data`, not the demo image's.)

**Шаг называет базу, в которой выполняется** — тем же полем `database`, что уже используют
проверки состояния; у первого шага (создание базы) этого поля нет, потому что базы ещё не
существует.

**Что считается успехом.** По умолчанию — сервер принял оператор. Необязательный `check`
у шага бывает двух видов: `expect = "rows"` (по умолчанию) — VQL, обязанный вернуть
непустой результат, разница между «объект создан» и «данные читаются»; `expect = "no
rows"` — для проверок вида «сломанного нет», например `GET_VIEWS(… invalid only)` обязан
быть пустым. Разница между «создан» и «читается» не косметическая: DF-источник, wrapper и
базовое представление над несуществующим файлом создаются без единой ошибки, и только
`SELECT` отвечает `Error executing query` (проверено на 9.5.1). У шагов, чей файл на
стенде отсутствует, `check` не ставится сознательно — их предмет синтаксис, а не данные.
(Since T40 only the JDBC templates point at a source that is not there: the DF and JSON
templates read the chain's CRM and order exports, and their checks count the rows.)

**Шаблон, который несёт креденшел, прогон шифрует сам.** Источник JDBC требует
`USERPASSWORD … ENCRYPTED`, и сервер проверяет шифр в момент создания: любую другую строку
он отвергает (`Invalid encrypted value`). Настоящий шифр в репозитории лежать не может — это
креденшел, и он привязан к выдавшему его серверу, так что чужому форку всё равно бесполезен.
Поэтому манифест объявляет намерение (`@encrypt-throwaway` в `[values]`), а прогон
подставляет значение: шифрует случайную пустышку на том стенде, куда собирается писать, и
выбрасывает её вместе с прогоном. Альтернатива — переписать шаблон на плейнтекст без
`ENCRYPTED` — кода не требует и проверяет меньше, чем заявляет единственная пометка блока.

**Цепочка внешнего элемента исполняется, хотя тело шага из ответа другого канала не
приходит.** Первое прочтение (T12) было: шаблон применяет VQL, сгенерированный ответом
`GET …/vql-metadata`, а исполнитель так не умеет. Оказалось, что ответ этого вызова —
контракт, который навык уже приводит **отдельным блоком**; шаг исполняет блок, а `vql-metadata`
остаётся вызовом, который надо совершить, а не телом, которое надо исполнить. Через каналы
передаётся не тело, а идентификатор, и это умеет `capture`. Цена ровно одна: каждый
идентификатор захватывается своим шагом, поэтому три шага делят один блок на четыре вызова, и
пометку блока не обновляет ни один — хотя вместе они исполняют его целиком. Правило «шаг
исполнил блок целиком» считает по шагу и этого случая не различает.

**The AI steps — behind `--with-ai`, off by default (T32).** A step with `ai = true` evaluates
an LLM or embedding function: it writes nothing outside the test database, but every row it
projects is a paid request to the provider the server is configured with, and a server without
that configuration or without the Enterprise Plus bundle fails it. A default run stays free and
portable, so these steps are skipped unless asked for, with the reason in the report; `ai` is
refused on an http step, which makes no such call. The embedding model the search-view
template names is read from the server (`@server`, T40) or set in the values file.

**The write steps — behind `--with-writes`, off by default (T33).** The templates of `dml`
change rows of a real table, and the only database every server has room for is its cache
database. A step with `writes = true` runs only with the flag: the `writes-tables` fixture
creates two tables there with `CREATE REMOTE TABLE` through the data source `[values]` names
(the server's cache data source, read from `GET_CACHE_CONFIGURATION()`; the identity key and
the timestamp of the DDL come from the manifest's dialect table of its product, T40), and base
views over them carrying the source's type
metadata, which `RETURNING` and `GET_VIEW_COLUMNS` need. `[cleanup] writes` — VQL run only under
the same flag, and **before** the rest of cleanup — drops both tables: `DROP_REMOTE_TABLE` drops
only a table `CREATE_REMOTE_TABLE` made, so each is first taken over by that procedure with
`replace_remote_table_if_exist`, then dropped with the base view it made, while `{database}`
still exists. A default run touches no source database at all; `writes` is refused on an http
step, which writes none.

The templates of `materialize` (T34) run behind the same flag, in the same place: a remote table
of the chain's `iv_household_income` and its `REFRESH`, a summary created unloaded and then
loaded — each checked by a plan, the unloaded one must not be used and the loaded one must —
a data movement that moves the band file next to the remote table, a materialized table, and
the drop of both tables. The template's warehouse data source and schema are substituted with
`[values]`'s, its table names take the `verify_` prefix, and `[cleanup] writes` takes both
names over with `CREATE_REMOTE_TABLE` and drops them again, so a run that stops halfway leaves
nothing in the cache database. A check can read the plan text:
`… FROM GET_QUERY_EXECUTION_PLAN() WHERE input_query = '…' AND execution_plan LIKE '%Summary
Acceleration%'` answers a row only when the optimizer chose the summary.

**The Testing Tool steps — behind `--testing-tool <dir>` (T35).** A `denodotest`-channel step
is a `.denodotest` block of `testing`: only the Denodo Testing Tool, a separate download with
Java, can say whether it passes, so a run without the flag skips these steps with the reason.
The block becomes the only file of a temporary folder, the tool's configuration is written
beside it by the code of `testing config` for the test database and removed with the folder,
and the launcher runs from the tool's `bin/` (it logs to `../log` of its working directory). A
step passes on exit code 0 **and** a summary of one test run and one OK: the launcher exits 0
after printing its usage, and a file it does not recognise is skipped. The plan template runs
over the remote table of the write steps, so it also needs `--with-writes`.

**The Scheduler tail — behind `--with-scheduler` (T36).** Its objects are server-wide like the
marketplace's, so a default run never touches them. The steps create a `verify_` project, a
cache job over `iv_household_income` while its full cache is on — created disabled, read back,
enabled, run twice, and the cache then holds every household once, which is the claim of its
`ALL_ROWS` line — a `PUT` of the job's file with its id that keeps the schedule, and a CSV
export job created, enabled and run. `[cleanup] http` deletes the project, its jobs and their
reports. Three mechanics came with it: an `api` line may name its server (`--server`) and read
its body from a file (`--json-file`), which the step maps to a json block of the same skill
(`files`), so the run sends the text the skill shows; a capture may read an earlier call of the
step (`capture_from`) and a value a step captures may be named by its own later calls; `poll`
repeats the step's last call until a field has a value — a started job runs on its own, and its
report exists only when the run ends — and `capture` and `expect_body` take nested fields
(`a.b.0.c`). The VDP data source the jobs run through is `[values] scheduler_data_source_id`,
the one whose login is the profile's user, read from the Scheduler (T40): creating one needs a
password. The export leaves one file in the Scheduler's default export
folder, overwritten by every run; no API call removes it.

**Any server runs it (T40).** The chain used to need the Denodo demo image: its CSV folder,
SQL Server DDL, one embedding model, one Scheduler data source id. Now `[values]` keeps only
what belongs to the chain, and a value of one installation is a marker the run fills in before
its first step — `@server` from read-only calls (`VALIDATE_MPP_LICENSE`, `GET_CACHE_CONFIGURATION`,
an allowlist of `GET_PARAMETER` properties, the Scheduler's `dataSources`; `denodo_cli/features.py`),
`@dialect` from `[dialects.<product of the write data source>]`. The values file beside the
profiles (`verify.toml`, one table per profile; `--values` names another) overrides them and the
manifest's `local_values` (where the fixtures are read from) — never the test database, the
prefix or a throwaway password, which decide what the run drops; `--database` overrides the file.
A value nobody filled in skips every step and `[cleanup] writes` statement naming it, with the
line to add — a text with a placeholder is never sent. `env check` reports the same probe as
`features`, and a step's `requires` (`enterprise_plus`, `llm`, `embedding`, `cache`,
`summary_rewrite`, `data_movement`, `impersonation`) skips it, with the reason, when the server
is known to lack one; unknown runs; `--without <feature>` rehearses a server without it. A skip
travels: a step names the earlier steps whose objects it uses in `needs`, and is skipped with
them; a value a skipped step would have captured is unresolved for the steps after it. A unit
test holds the manifest to that statically. The fixtures read synthetic files under the TPC-DS names
(`verification/data`, written by its `generate.py`; the two the TPC-DS definitions fix are
byte-identical to the demo image's) over HTTP from the public repository, or from a copy on the
server's disk. **Every block of `skills/` marked `verified:` is a step, or a key of `[not_run]`
with the reason** — grammar, a fragment, the server's own message, a line for the human;
`tests/test_chain_manifest.py` holds both directions. The report adds `values_from`,
`unresolved`, `features` and `summary.not_run`. Measured on 9.5.1, every tail: the demo image
(SQL Server cache, fixtures over HTTP) and the same server with its cache database switched to
PostgreSQL (fixtures from a local folder). Detail:
[2026-10-06-portable-verify-design.md](2026-10-06-portable-verify-design.md).

**Маркетплейс — по флагу `--with-marketplace`, по умолчанию выключенному.** Его объекты
серверные, а не пообъектные по базам, и цепочке предшествует синхронизация общего
каталога — единственная операция набора, меняющая состояние за пределами своей базы.
Базовый прогон обязан оставаться безопасным. Шаг HTTP-канала умеет захватить
идентификатор из ответа (`capture`): следующий шаг и уборка иначе не знают, что удалять.

**An http step can also assert on its last response (`expect_body`, T30).** `capture` only
records; it never judges. The rename template's whole claim is that a field survives — the
marketplace element keeps its id when the old and new names are matched in the
`synchronize` call — and a run in which the server ignored the pair would hand out a new id
and still report every call `2xx`. `expect_body = { id = "{renamed_view_id}" }` compares a
top-level field of the last call's body with a value rendered from `[values]` (including
what earlier steps captured) and fails the step, naming both, when they differ or the field
is missing. It is a comparison, not a branch: the step model still cannot "read, then
decide", for the reason given below. It is refused on a vql step, which has no response body
to compare. The value `<absent>` asserts the opposite — the field must not be there (T43): a
removal is proved by what is gone, `"0" = "<absent>"` on a list the step emptied.

**Хвост маркетплейса не идемпотентен, и это принятое свойство, а не пробел.** Шаг тега
исполняет lookup и create безусловно, у шага категории lookup-вызова нет вовсе, а модель
шага не умеет «прочитать, потом решить»: ветка по ответу превратила бы манифест в
интерпретатор, которого этот раздел избегает. Поэтому второй прогон поверх объектов,
оставленных `--keep`, падает на `409` (дубликат имени). Громкий отказ выбран сознательно —
альтернатива, уникальные имена на каждый прогон, коллизии бы убрала, но объекты каждого
`--keep`-прогона тихо накапливались бы в **общем** каталоге маркетплейса, и заставить их
убрать было бы уже нечему. Требование к такому отказу одно: он обязан объяснять себя.
`409` приходит с пустым телом, поэтому ошибка http-шага несёт `hint` — причину и два
`DELETE`, которыми остаток убирается руками (T17). Цена решения называется прямо: ветка
`PUT` шаблона тега цепочкой не исполняется, то есть правило самого навыка `marketplace`
(«всё, что запускается дважды, читает перед записью») ею не проверяется.

**Уборка выполняется всегда**, кроме явного `--keep`: сперва VQL — `DROP DATABASE
<тестовая> CASCADE` и теги, — потом HTTP: обратный проход по захваченным идентификаторам
маркетплейса и **повтор тех же вызовов `synchronize`**, которыми цепочка начиналась.
Порядок обязателен и содержателен: синхронизация убирает из каталога маркетплейса то,
чего больше нет в VDP, поэтому после `DROP DATABASE` она означает ровно обратное тому,
что означала в начале прогона, — тестовая база и её представления уходят из общего
каталога. Без этого шага прогон оставлял их там сиротами (`localElements` в `.../changes`)
и при этом рапортовал об успехе. HTTP-часть уборки идёт под тем же флагом
`--with-marketplace`, что и шаги, которые она отменяет: базовый прогон в каталог ничего не
писал, и трогать общий каталог ему незачем. Результат уборки — часть отчёта, а не строка
в логе: прогон, не убравший за собой, обязан это сказать.

**Прогон против production-профиля отклоняется целиком, до первого шага.** `CREATE OR
REPLACE` разрушительным не считается (раздел 6.3), поэтому проверка «по каждому вызову»
пропустила бы всю цепочку — база, представления и два *серверных* тега были бы созданы —
и отказала бы только уборке, гарантированно оставив ровно те объекты, ради удаления
которых команда и существует. Отказ поэтому накрывает прогон целиком: `error.kind =
"refused"` и код выхода 2, как у любой отклонённой разрушительной операции, ничего не
отправлено. Снимается флагом `--allow-destructive` — и тогда он же передаётся дальше,
каждому разрушительному вызову прогона и его уборки.

**Пометки правит флаг, а не каждый прогон.** `--update-marks` переписывает строку
`-- verified: <версия> (live, <дата>)` только у успешных шагов вида `template` и только
внутри блока кода, из которого шаг читает тело; версия берётся из ответа сервера. И только
если шаг исполнил блок целиком: у HTTP-шага `calls` называет подмножество вызовов блока
(шаг тега — два из четырёх, шаг категории — один из трёх), а пометка у блока одна, и
переписать её по такому прогону значило бы заявить больше, чем он проверил. Такой шаг
пишет в отчёт `reason` и пометку не трогает — как и шаг, для которого не удалось прочитать
версию сервера. Те же
факты, повторённые прозой рядом с таблицами (`*verified: 9.5.1 (live, …)*`), флаг не
трогает — это правка руками, потому что переписать их значило бы утверждать то, что прогон
не проверял. Иначе прогон против сломанного или чужого стенда разом сорвал бы в
`unverified` набор, собиравшийся неделями, — а так правка видна диффом до коммита.

### 11.2 Eval-сьют: срабатывает ли нужный навык

Набор фраз → ожидаемый навык, прогон через `claude plugin eval`. Регрессионный тест на
описания: когда после v1 добавятся `security` или `performance`, их `description` начнут
конкурировать с существующими, и без сьюта деградация пройдёт незаметно.

### 11.3 Outcome scenarios: what the agent does next (T42)

The routing suite says which skill fires; six scenarios say what the agent then does, against a
test server: a mart from CSV files, a full cache on the agent's own view, a metric view and a
figure from it, a write through `dml` in two turns (the request, then the yes), a view published
in the marketplace with a new tag, and two `DROP`s asked for under a deadline. Each is a human's
request run by headless Claude Code with the plugin, and graded by a program on the trace (the
tool's own JSON per statement: its text, `ok`, class and source), the session's ledger, the files
the agent wrote and the server's state after the run; an LLM judge only for what none of these
shows. Fixtures are `verify` manifests on `eval_` databases, reset before every run (`verify
--cleanup-only`, then `--keep`). The scenarios run under `evals/outcome/run.py`, not `claude
plugin eval`: an eval case that grants `Bash` runs it in an OS sandbox whose network is an HTTP
proxy allow-list, and the tool's connection to Virtual DataPort is the PostgreSQL protocol
(measured on Claude Code 2.1.291). Run before a release, not in CI. The detail, the checks and
the measured cost: [the T42 design](2026-10-06-outcome-evals-design.md) and `evals/README.md`.

## 12. Границы v1

**Входит:** ядро, слой исполнения, `catalog` (виртуальные базы, папки, теги VDP),
`datasources` (источники JDBC, DF и JSON с их wrappers и базовыми представлениями),
`views` (derived, interface, ассоциации), `marketplace` (теги, категории, external
elements Data Marketplace), `query` в объёме минимальной дельты, верификация и eval-сьют.
(The dialect ended up as `vql/references/dialect.md`, T24 — section 9.)

Полный перечень — шестнадцать объектов с командами, каналами и способом верификации
каждого — вынесен в отдельный документ: [объём v1](2026-09-04-denodo-v1-scope.md). Там же
порядок сборки: ядро из шести объектов доводится до работающего сквозного сценария
раньше, чем пишется остальное.

**Не входит:**

- полный справочник функций;
- производительность и кэш — summary views, materialized tables, remote tables, MPP;
- безопасность и публикация — пользователи, роли, привилегии, row/column restrictions,
  REST/SOAP/GraphQL/OData сервисы;
- Solution Manager, деплой между средами (Scheduler — beyond v1 since T36, below);
- flightsql-транспорт (заложен структурно, но не реализуется);
- собственный MCP-сервер;
- версии Denodo кроме 9.5.

**Сверх v1 в наборе есть `/denodo:procedures`** (T14): хранимые процедуры в сценарии
витрины не участвуют и в перечень шестнадцати не входят, но как навык полезны сами по
себе. Добавлены тем же способом, что и остальные, — новым каталогом в `skills/`, без
правки ядра и формата навыка. Слоя исполнения это стоило одной правки: тело VQL-процедуры
несёт собственные `;`, и сплиттер научился держать его целым.

**Also beyond v1, `/denodo:cache`** (T27, from the owner's roadmap review): the full cache of
a view only — switching it on and off, loading it with the rows the human names, clearing
it. Partial cache, time to live, incremental loads, cache indexes and scheduled refreshes
stay in Design Studio and Scheduler. It cost the execution layer one classifier rule (the
load query, section 6.3); its three templates run in the `verify` chain.

**Also beyond v1, `/denodo:semantics`** (T28, from the owner's roadmap review): the Virtual
DataPort half of what AI consumers read — an audit of a database for view, field, association
and tag descriptions, primary keys, missing associations and the MCP visibility tag, and the
metadata written with `ALTER` or in the view's own file once the human approves the texts.
Logical names, property groups and marketplace-side descriptions wait for a `marketplace`
extension. It cost the execution layer nothing: every statement it writes is an `ALTER`,
already classified; its three templates and the claim that re-applying a view's file removes
the metadata run in the `verify` chain.

**Also beyond v1, `/denodo:metrics`** (T29, from the owner's roadmap review): metric views —
KPIs declared once over a fact view and its dimension views, queried with `evaluate_metric`.
The owner's rule is its core: the only thing built directly on a metric view is a selection
view; other facts, dimensions, metric views and arithmetic over metrics go over selection
views (confirmed live: a metric view joined in the same `FROM` runs until the query timeout,
and an expression around `evaluate_metric` is dropped). It cost the execution layer nothing —
`CREATE OR REPLACE METRIC VIEW` is a `CREATE`, classified as such; changing someone else's
metric view is in the safety table of `vql`. Its five templates, each with a check that the
totals agree, run in the `verify` chain, whose fixture now declares the key of
`bv_income_band` (a dimension view without one empties every `HAVING` grouped by its key).

**Also beyond v1, `/denodo:security`** (T31, from the owner's roadmap review): a role with
read access given to a user, a global security policy that masks columns, filters rows or
denies a view over tagged columns, and the check as each person. Two facts carry it, both
measured on 9.5.1: administrators — global, and local ones of the view's database — are
never restricted, so the agent's own `SELECT` proves nothing; and an audience restricts only
the grant path it names (a role audience what roles grant, a user audience what is granted
directly, `ALL` every path), so one person with a direct grant reads in clear under a policy
that "works". The check is `CONTEXT ('impersonate_user' = …)` — the owner granted the
`impersonator` role to the profile user of the test server for it — instead of the second,
non-administrator profile the roadmap asked for (decision 9.3): impersonation checks every
person and role without a password, a second profile one account and with one. Global
objects (decision 9.2): the agent applies a security statement itself only when everything
it touches was created in the same session; anything that existed before, any grant to a
person, and any new policy that reaches existing people or views waits for the human's yes,
a `CREATE` included. On the test server, server-wide objects are the run's own by prefix
only (`verify_`, `zq<task>_`), and the users a check reads as are `EXTERNAL`, so no password
exists. It cost the execution layer the `security` kind in the classifier (section 6.3) and
the two flags of `env check` (section 7.3); its four templates and the claim that
re-applying a view's file takes the mask away run in the `verify` chain, whose checks read
as an `EXTERNAL` user by impersonation.

**Also beyond v1, `/denodo:ai`** (T32, from the owner's roadmap review): the six LLM functions
of VQL over a text column (`CLASSIFY_AI`, `SENTIMENT_AI`, `SUMMARIZE_AI`, `TRANSLATE_AI`,
`EXTRACT_AI`, `ENRICH_AI`), a view that keeps their answers in its full cache, and semantic
search over a vector column a database already stores (`VECTOR_DISTANCE`, `EMBED_AI`, the
distance functions), including a search view an application passes a sentence to. The owner's
rule is its core: an AI function runs over rows only up to a number the human agreed to,
because every row is a paid request whose text leaves for an outside provider; `vql` carries it
in its safety table. What makes the rule enforceable is measured on 9.5.1: a `LIMIT` bounds the
requests only when the function is in the `SELECT` list alone — under `ORDER BY` or `GROUP BY`
every row is sent, and a condition on an AI result is pushed down and evaluated before the other
filters, over every row of a file source; the tool's `--max-rows` cuts the printout, not the
work; a view parameter passed to `VECTOR_DISTANCE` is embedded once per row on every search,
the documentation's own pattern; and a reader of a view with an AI column needs the
`use_large_language_model` role unless the view is cached. It cost the execution layer no
classifier rule — an AI call changes no state, and a text classifier cannot see the rows it
will touch — and the verification chain one flag, `--with-ai` (section 11.1), behind which its
seven templates run over a six-row fixture.

**Also beyond v1, `/denodo:dml`** (T33, from the owner's roadmap review): rows changed in the
database behind a view — updating, inserting with the generated key back, deleting, by key; a
view an application writes through, with `WITH CHECK OPTION`; rows copied from another view or a
file, and the upsert. The safety of writes to sources was left by the owner for later, so the
skill keeps `vql`'s rule as it stands — every write waits for the human's yes to the exact
statements — and makes the yes informed: a preview `SELECT` with the write's `WHERE`, a
before-image saved as the undo, and what the readers will see. Measured on 9.5.1 against SQL
Server: over the tool's connection `ROLLBACK` answers `ok` and undoes nothing; a write through a
view with a full cache, or through any view above one, empties that cache for everyone until
its next load, while a write below it leaves it stale; `WITH CHECK OPTION` evaluates the view's
filter on the statement's values only, so a `NULL` (a column left out) passes; impersonation
does not reach writes; `RETURNING` answers for a one-row insert of the generated key and fails
or returns nothing otherwise, and on a base view without the source's type metadata it fails
after inserting the row; an upsert keyed on an identity column fails; the source's own refusal
of a value arrives cut. It cost the execution layer the `affected` field (section 7.3) and the
verification chain `--with-writes` (section 11.1), behind which its seven templates run against
two tables created in the cache database; no classifier rule — `INSERT`, `UPDATE`, `DELETE` were
already flagged.

**Also beyond v1, `/denodo:materialize`** (T34, from the owner's roadmap review): the result
of a query stored as a table — a remote table other tools read, created by `CREATE_REMOTE_TABLE`
and reloaded by `REFRESH`, a frozen snapshot, a summary the optimizer answers aggregate queries
from, a data movement that copies the small side of a federated join next to the big one, and
a materialized table. Its rule is the owner's decision on writes to external databases
(section 6.3): a new table where the human said is the agent's, anything older and every load
of a summary is the human's. Measured on 9.5.1 against SQL Server: `REFRESH` empties the table
first and leaves it empty when the load fails (a source down; a column added under a `SELECT *`
load query); a load that fails after the table was created leaves it empty without a base view;
the `CREATE REMOTE TABLE` command makes no base view, reports no count and its table can be
neither refreshed nor dropped by `DROP_REMOTE_TABLE`; `OR REPLACE` replaces another reader's
table and its base view stays `OK` until a dropped column is queried; a remote table is not in
`USED_BY` of the view it is loaded from; a summary keeps answering its last load after rows
changed and after the view under it was re-declared with a new filter — the documented
invalidation was not observed — and a summary whose load failed stays in every plan, empty, so
the queries it answers return no rows and a total `NULL` while the sources are fine; a summary
answers `COUNT(DISTINCT)` only at exactly its grain and never `AVG`; filters answered from a
summary or a remote table follow that database's collation; characters outside the code page
land as `?` in a `varchar` column; a data movement into a data source the big side is not in
moves for nothing; `CREATE OR REPLACE MATERIALIZED TABLE` over rows empties it. It cost the execution layer the `table` kind of the classifier and
the verification chain eight steps behind `--with-writes`.

**Also beyond v1, `/denodo:testing`** (T35, from the owner's roadmap review): regression tests
for data products in Denodo's own format, `.denodotest` files beside the project's `.vql`, run
by the Denodo Testing Tool — no runner of the plugin's own. Its first tests are the checks
`views` makes at creation time, kept: a mart's totals against its input, a unique key, nothing
`INVALID`, the contract's columns, the rows a consumer reads, a plan that stays in its database.
Its rules come from the baseline: a copy of today's rows comes after the totals test passes,
or it pins the defect it should catch; each new test is seen failing once; a red test is a
finding about the views or about the test, decided before anything is edited, and fixing a
view that existed before the session is not fixing the test. Measured against the tool
(release 20260428) and 9.5.1: inline data is compared in order unless told otherwise, columns
by name, `NULL` equal to `''`, a `timestamp` only as `yyyy-MM-dd HH:mm:ss.SSS`; a subset of
nothing passes; a line starting with `#` is a comment inside data too; `%TRACE` fails every
test it is in; a failed `SETUP` or `RESULTS` query skips the `TEARDOWN`; the launcher exits 0
after printing its usage. It cost the execution layer `testing run`, `testing config` and the
profile's `jdbc_port` (section 7.4), and the verification chain the `denodotest` channel behind
`--testing-tool` (section 11.1), which runs its six templates through the code of `testing
run`.

**Also beyond v1, `/denodo:scheduler`** (T36, the roadmap's "later" item 4.12, taken as the
next task once every wave was closed): work on a schedule through the REST API of the Denodo
Scheduler administration tool — a cache job that reloads the full cache of views, a VDP job
that runs one statement (`REFRESH`, a `CALL`) or exports a `SELECT` to a CSV file on the
Scheduler host; running, stopping, enabling and disabling a job; its status and reports.
Data sources (they hold a password), the other job types, other exporters, handlers, retries,
trigger conditions, dependencies and the server's configuration stay in the administration
tool. Its rule: a job is its statement, run every time it fires — created disabled by the
agent, enabled on the yes its statement needs. Measured on 9.5.1: a new cache job's
invalidation mode is `NONE` in the API and in the 9.5.1 administration tool, against the
documentation's *Matching rows* — every run appends and reports `COMPLETE`; a load process
without `loadProcessName` or `parameterizedQuery` is accepted and fails every run; a trigger has
no time zone, the cron fires on the server's clock and `nextExecution` is UTC; a five-field cron
and a `start` of a disabled job answer only `500 Internal error`; a `PUT` replaces the whole job
— without `triggerSection` the job loses its schedule, without `handlerSection` the call fails;
an unescaped `@` fails every run, not the creation; the CSV exporter by default writes no header
and a new timestamped file per run, and with `allowEmptyFile: false` an empty run deletes the
previous file; a job may use a VDP data source of another project, and runs as its login in the
database of its URI; a run's report exists only when it ends. It cost the execution layer the
Scheduler transport, the profile's `scheduler_url` and `scheduler_uri`, the classifier's
Scheduler rules with the `job` kind, the `scheduler` section of `env check` and the refusal of
`..` in a path (section 7.3), and the verification chain the Scheduler tail behind
`--with-scheduler` (section 11.1).

## 13. Риски и открытые вопросы

**Риск №1 — пропускная способность канала для DDL. Снят (T2, [отчёт](2026-09-08-spike-t2-ddl-over-9996.md)).**
Через `denodo+psycopg2` на порту 9996 прошла вся VQL-цепочка v1 от `CREATE DATABASE`
до `CREATE ASSOCIATION`, включая теги и `DESC VQL`. `api_rest` нужен только Data
Marketplace. Оговорки для слоя исполнения — автокоммит через событие `connect`,
обработка `%` в psycopg2, `CONNECT DATABASE` и `DROP DATABASE` — в разделе 3 отчёта;
проверялось под администратором, поведение под ограниченной ролью не смотрели.

**Риск №2 — недокументированный API маркетплейса. Снят (T11, [отчёт](2026-09-08-spike-t11-marketplace-api.md)).**
Пути и тела для тегов, категорий и external elements сняты с OpenAPI живого сервера
(`/v3/api-docs`) и подтверждены прогоном: HTTP Basic учёткой VDP на каждом запросе,
`serverId` необязателен при одном сервере и обязателен при нескольких (T8d: без него
`500 «Session Expired»` на тегах и `403` на external tool server'ах), импортированные из VDP теги в маркетплейсе
только на чтение — развилка `catalog` ↔ `marketplace` из раздела 4 стоит на проверенном
факте. Две поправки к ожиданиям: external element в 9.5 не создаётся одним вызовом, а
импортируется из interface view VDP через custom external tool server (раздел 8), и среди
разрушительных операций есть `POST` без единого слова `DROP`/`DELETE` — правило 6.3
строится по методу и пути, а не по глаголу. Проверялось под администратором, OAuth и
несколько серверов VDP не смотрели.

**Закрыто:** точный перечень объектов v1 — см. [объём v1](2026-09-04-denodo-v1-scope.md).

**Закрыто (T2):** поведение `CREATE OR REPLACE` и применимость `IF EXISTS` ко всем
типам — см. 6.4.

## 14. Приложение: отвергнутые альтернативы

### 14.1 Нарезка навыков

**A. Один зонтичный навык с большой библиотекой references.** Постоянная стоимость —
один `description`. Отвергнут: агент всегда делает два чтения, `SKILL.md` разрастается в
оглавление, единственный триггер срабатывает либо слишком часто, либо слишком редко.

**B. Много мелких навыков по классам объектов без общего ядра.** Точные триггеры, одно
чтение. Отвергнут: общее — подключение, исполнение, конвенции именования,
идемпотентность, разбор ошибок — дублируется в каждом навыке и рассинхронизируется при
обновлении, а близкие описания заставляют агента промахиваться.

### 14.2 Транспорт

**JDBC.** Требует Java и `denodo-vdp-jdbcdriver.jar`, который нельзя распространять в
публичном open-source плагине по лицензии Denodo.

**Вендоринг pure-Python драйвера.** Denodo слушает PostgreSQL wire protocol на порту
9996, поэтому теоретически подходит `pg8000` (BSD 3-Clause, 58 КБ, колесо `py3-none-any`,
то есть без C-расширений) вместе с `scramp`, `asn1crypto` и `python-dateutil` —
суммарно около 440 КБ, все лицензии допускают вендоринг, установка не требуется вовсе.
Отвергнут: Denodo реализует протокол PostgreSQL частично и официально поддерживает
psycopg2, а не произвольный клиент, — риск не оправдан; кроме того теряется
расширяемость экосистемы SQLAlchemy.

### 14.3 Конвенции

**Только жёсткие дефолты без переопределения.** Проще всего, но команды со своими
стандартами будут бороться с плагином.

**Всегда выводить конвенции из живого каталога.** Самое естественное поведение, но
стоит токенов на каждой сессии и не работает на пустом стенде.

## 15. Источники

- [Virtual DataPort VQL Guide 9.5](https://community.denodo.com/docs/html/browse/latest/en/vdp/vql/index)
- [Denodo Dialect for SQLAlchemy — User Manual](https://community.denodo.com/docs/html/document/denodoconnects/8.0/en/Denodo%20Dialect%20for%20SQLAlchemy%20-%20User%20Manual)
- [Denodo MCP Server — User Manual](https://community.denodo.com/docs/html/document/denodoconnects/9.2-beta/Denodo%20MCP%20Server%20-%20User%20Manual)
- [Denodo AI SDK — User Manual](https://community.denodo.com/docs/html/document/denodoconnects/latest/en/Denodo%20AI%20SDK%20-%20User%20Manual)
- [Claude Code: plugins reference](https://code.claude.com/docs/en/plugins-reference)
- [Claude Code: plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
- [Claude Code: skills](https://code.claude.com/docs/en/skills)
