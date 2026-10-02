# Трекер задач

Источник истины по архитектуре — [дизайн-документ](superpowers/specs/2026-09-04-denodo-skills-design.md).
Перечень объектов v1 — [объём v1](superpowers/specs/2026-09-04-denodo-v1-scope.md).
Рабочий процесс (ветка на задачу → PR с описанием сессии) описан в [CLAUDE.md](../CLAUDE.md).

Статусы: `сейчас` — в работе, `дальше` — готова к взятию, `ждёт` — заблокирована другой
задачей, `сделано` — закрыта.

**Вехи.** Веха A — сквозной сценарий работает на цепочке из шести объектов — **закрыта
2026-09-12 приёмкой T13**. Веха B — полный перечень из шестнадцати, включая Data Marketplace,
— **закрыта 2026-09-12 приёмкой T19**.

---

## Дальше

Очередь собрана по итогам поштучного ревью роадмапа с владельцем (2026-09-29):
[роадмап](superpowers/specs/2026-09-29-denodo-skills-roadmap.md), решения — в его разделе 11,
порядок волн — в разделе 10. Задачи идут в порядке волн; ссылка «р. 4.6» — раздел роадмапа.
Каждая задача, меняющая `description`, гоняет eval-сьют.

**Волна 0 — ядро и существующие навыки.**

*Wave 0 is done: T22, T23 and T24 are under «Сделано» below.*

**Волна 1 — `views`.**

*T25 is done — under «Сделано» below.*

*T26 is done — under «Сделано» below. Wave 1 is closed.*

**Волна 2 — новые навыки на VQL.**

*T27 is done — under «Сделано» below.*

*T28 is done — under «Сделано» below. The marketplace half of `semantics` (logical names,
property groups, sync pitfalls) is still to come, as a `marketplace` extension.*

*T29 is done — under «Сделано» below. Wave 2 is closed.*

**Волна 3 — маркетплейс.**

*T30 is done — under «Сделано» below. Wave 3 is closed.*

**Волна 4 — навыки, которым сначала нужно решение или установка.**

*T31 is done — under «Сделано» below.*

*T32 is done — under «Сделано» below.*

- **T33. Навык `dml`.** `дальше`. `INSERT`/`UPDATE`/`DELETE` через представления, `RETURNING`,
  `WITH CHECK OPTION`. Безопасность записи в источники владелец решает позже; классификатор
  помечает `INSERT`/`UPDATE` уже после T22. Р. 6.
- **T34. Навык `materialize`.** `дальше`. Удалённые и материализованные таблицы, summaries,
  data movement. Удалённая таблица пишет в базу-источник с `DROP` и `TRUNCATE` внутри —
  решить в задаче запись во внешние базы (р. 9, решение 2) и добавить
  `CREATE [OR REPLACE] REMOTE TABLE` и `REFRESH` удалённой таблицы в классификатор. Р. 5.3.
- **T35. Навык `testing`: формат `.denodotest`, исполняет Testing Tool.** `дальше`. Тесты
  рядом с `.vql` проекта, первые — проверки, которые `views` уже делает при создании.
  Своего раннера нет. Решить в задаче: как получить `configuration.properties` вне
  репозитория так, чтобы пароль не попал ни в git, ни в командную строку. Р. 4.9.

**Позже:** `scheduler` — отдельным навыком (р. 4.12). Снятое на ревью перечислено в разделе
10 роадмапа.

---

## Открытые вопросы

- **A matched-rename synchronisation is still the human's yes — should it be?** (T30, for the
  owner.) A `VIEWS/synchronize` whose only `localElements` entry is the old name of a pair it
  matches, and whose `modifiedElements` are only marketplace-edited descriptions, removes
  nothing and keeps everything; one GREEN run of T30, under an earlier wording of the skill,
  ran it alone for a human who was away with a deadline, and the outcome was right. The skill
  now keeps the `vql` rule — every `synchronize` waits for a yes, and when asking is
  impossible the body goes into a file — so the analysts in that scenario wait for the human.
  A second named exception, beside the first import of a new tool server, would change that.
- **Two answers to "may the agent synchronise"** (T30, found by a GREEN review, older than
  T30). `vql` puts every `synchronize` under the human's yes; `marketplace`'s slot table asks
  the human only "if `changes` shows anything under `localElements` or a modified element that
  is not yours", which reads as "otherwise go" — the case of synchronising so that a new view
  gets an id for a tag. T30 aligned only its own rename text with `vql`.
- **A yes given in advance** (T30, raised by a GREEN review). `vql` defines the confirmation as
  a yes "after you have shown the exact statements or calls"; it does not say whether a yes
  that names the operations up front ("create it there, drop it here, synchronise") from a
  human who will not be reachable counts. The GREEN run that had one treated it as enough,
  each synchronisation only after its radius held nothing but its own view — reasonable, and
  not written anywhere.
- **Moves across databases in the marketplace UI** (T30): the REST call ignores a pair whose
  databases differ, silently, twice. Whether the UI's drag-and-drop accepts such a pair, and
  what it does then, was not tried. Renamed web services (`WEBSERVICES/synchronize` with a
  pair) were not tried either.
- **Grants after `ALTER VIEW … RENAME`** (T30, raised by a GREEN review): whether privileges
  granted on the view follow it to the new name was not checked.
- **`PUT /public/api/views/fields/logical-name` answers `200` and stores nothing** (T30, one
  try): `logicalName` stayed `null`. Probably the marketplace personalisation has logical names
  off; it belongs to the marketplace half of `semantics`, still to come.

- **A sample over rows needs the human's number too — is that what the owner wants?** (T32,
  for the owner.) The skill reads the rule "never an AI function over a table without a
  `LIMIT` the human agreed to" strictly: without a number the agent may only try an expression
  on `Dual()` with up to three texts; a vague "a handful" is at most five rows. Under a
  deadline with the human away, every GREEN and Sonnet run therefore delivered the files, the
  `Dual()` tries and the message, and no counts — for a 296-request run. A named ceiling ("up
  to 400, no need to come back") is a number, and the control runs used it.
- **`vql`'s `ALTER` row and objects created in the session** (T32, from a GREEN review). The
  safety table puts "`ALTER` of an object that already exists" under the human's yes, while
  `cache`, `ai`, `security` and `metrics` let the agent alter what it created in the same
  session (`ALTER VIEW … CACHE FULL` on its own new view). Read literally, the core row blocks
  the second line of the `ai` and `cache` templates; nobody ran into it, everybody noticed it.
- **What `ai` leaves untried** (T32): the error texts on a server without an LLM or without
  Enterprise Plus (this one has both); `ENRICH_AI_BINARY`; `SENTIMENT_AI` with a custom scale;
  approximate search and `CONTEXT ('approximate_vector_search' = 'OFF')`; a data source with
  `delegatevectorliteral = true` (every vector source on the server is another team's, set to
  `false`); `EMBED_AI` delegated to a source; a request for several labels per row, which
  `CLASSIFY_AI` cannot answer.
- **A condition on an AI column over a file source runs before the other filters** (T32,
  measured, not explained): the plan lists `sentiment_ai(…) is not null` first among the
  base's filter conditions, and 4 wanted rows cost 39 requests over a 35-row file. Over JDBC the
  other filters went to the database and the same query cost 8.
- **`vql desc --vql` prints a dependency's data source** (T32, from a GREEN review): on an
  interface view it printed the JDBC URI, user and encrypted password of the other team's data
  source into the transcript. `('includeDependencies' = 'no')` exists and `views` uses it;
  `execute` does not mention it.
- **The server adds `TIMETOLIVEINCACHE NOEXPIRE` to a cache line** (T32, three runs): `DESC VQL`
  of a view switched on with `ALTER VIEW … CACHE FULL WITH_STATUS` ends with it. Harmless, and
  not in `cache`.

- **Column privileges behave unlike the documentation** (T31). A role with `EXECUTE` on the
  database and `GRANT EXECUTE ( a, b ) ON db.view` was refused the other columns (`does not
  have privileges to project these columns`) — the documentation says element privileges
  are ignored while the database grant is there. A role with only `CONNECT` and the same
  column grant could not read the view at all (`does not have EXECUTE privileges on the
  view`). Column privileges are left to Design Studio in `security`; the second answer is
  unexplained.
- **What `security` leaves untried** (T31): session-attribute (`ABAC`) audiences, custom
  policies, `COLUMNS TAGGED TOP_VIEW` (needs a server property), per-role row restrictions
  (`GRANT EXECUTE WHEN … THEN …`), and roles that arrive from an identity provider or LDAP —
  whether such a role is one more grant path a role-audience policy misses, as two runs
  asked. A non-administrator with the `impersonator` role and the server property
  `allowImpersonateToRegularUsers` was not tried either; `env check` would report what the
  server answers.
- **A tag that switches a mask on carries no `destructive` flag** (T31, from a GREEN review).
  `CREATE OR REPLACE TAG … ADD_TO` on a tag a policy names restricts a column for real people
  and comes back `destructive: null`; only `ALTER TAG` is flagged. A text classifier cannot
  know which tags policies name; asking the server before applying would mean a classifier
  that reads the catalog. The rule lives in `security` and `catalog` instead.

- **Metric views: three behaviours measured, not explained** (T29). (1) An association between
  the fact and the base view under a dimension view turns the metric view's `RIGHT` into
  `INNER` (reproduced by adding and dropping it); why that association is consulted at all is
  unknown. (2) A `HAVING` on a metric grouped by the key of a dimension view without a declared
  primary key plans as `INCOMPATIBLE_QUERY_VIEW` over file sources, but answers over a view
  delegated to SQL Server — only those two cases were measured. (3) An expression over a
  dimension grouped by its alias drops every `COUNT(DISTINCT …)` metric from the plan over SQL
  Server sources and keeps it over file sources; PostgreSQL was not tried. The skill states each
  as measured, with the condition it was measured under.
- **The `FILTER ( … )` clause of a metric view** (T29) is not in the VQL grammar; the wizard
  writes it. Over one source every query fails with `Error applying metric transformation.`,
  over two a metrics-only query fails when the condition is on a fact column. The skill sends
  filters to the fact view instead. A metric view saved from the Design Studio wizard with a
  filter would show whether the wizard's own output works — not tried.
- **Consumers of metric views were not queried** (T29): the Data Marketplace query wizard,
  Assisted Query's dimension/metric flag, Power BI in DirectQuery mode, the MCP Server, and
  summaries over a metric view are all from the documentation.
- **The association template of `views` declares `(1)` on the principal end** (T29). Over a
  fact with `NULL` or orphan keys, any metric view over it drops those facts whatever join type
  it writes; `views` now says so next to the template, and `metrics` tells the agent to write
  `(0,1)`. Whether the template itself should switch to `(0,1)` — an association does not make
  joins written by hand implicit, so only metric views would notice — is open.

- **The consumer side of `semantics` is documentation only** (T28). No MCP Server, Assisted
  Query or AI SDK was queried: that a column-level tag leaves a view hidden, that the MCP
  Server shows inherited field descriptions (JDBC `REMARKS`), where its "sample values" come
  from, and that the AI SDK pointed at a database reads its base views are all from the
  manuals. The server has an AI SDK container beside it; a `getMetadata` run against a
  fixture database would settle the last two, and a local MCP Server the first two.
- **The `views` mart template averages a sentinel** (T28): `household_income_by_band.avg_vehicles`
  is `AVG(vehicles)` over a column where the source holds `-1` for a sixth of the rows, so the
  average is pulled down. The template is about the join and the grain; whether to exclude
  `-1` there, and what `-1` means, was left open. The `semantics` write template describes
  `avg_dependents` instead, which has no sentinel.
- **The current row of a dimension that keeps history** is not in `views` (T28, one run): the
  skill says how to recognise history (validity columns, the count) but not how to pick
  today's row — in the demo store export the open version has `''`, not `NULL`, as its end.
- The endpoint line of `views` ("what you reach FROM the other side — i.e. the other view's
  name") read backwards to one T28 run; it followed the template's example instead.

- **The physical cache tables were not observed** (T27). The auto-mode classifier refused
  `DROP_NONACTIVE_CACHE_TABLES` even in preview mode, and the cache database has no
  credential the session may read, so "the empty table stays until the view is dropped" is
  documentation-only in `cache`. The `NO_STATUS` runs of T27 swapped cache tables several
  times; any table left behind is in the server's cache data source under a `C_WRL_NS…` or
  `C_WEB_RETURN_LINE…` name. A preview of `DROP_NONACTIVE_CACHE_TABLES` by the owner would
  show both.
- **A delimiter inside quoted values parses** (T27, two subagents independently over a demo
  item file: 18,000 rows, values in the right columns, the unchanged DF template), while
  `datasources` sends such files to Design Studio as unverified. A line break inside quotes
  is still unchecked. Splitting the rule needs its own check, not a subagent's. *T31:* a
  third subagent applied the unchanged template to a demo call-centre file whose quoted
  values carry commas and compared every cell with a CSV parser — 186 of 186 matched — and
  said the rule, taken literally, would have left an unreachable human with nothing.
- **`ds_<source system>` for a lone file** with no system name (T27): the run invented one.
  The naming table has no default for it.
- **Privilege narrowing of the dependency procedures** (T26) — *mostly closed in T31* by
  impersonation: `COLUMN_DEPENDENCIES()` as a user who reads only the top view answers
  nameless `No Privileges` rows, `USED_BY()` of a view the user cannot read fails with a bare
  `Error executing query`. Still documentation only: a dependant the user cannot see being
  left out of a `USED_BY()` answer whose input view they can see.
- **Mart questions the T26 runs kept raising, outside its scope:** whether "for every store
  and month" means a full grid or only the cells with data, and what primary key a line-grain
  view gets when the source has no unique key (`views` templates always declare one). Five
  runs decided each on their own, all the same way (cells with data; no key, said in the
  `DESCRIPTION`); neither is in the skill.

- `env.database` в JSON-конверте `scripts/denodo` показывает базу из профиля, а не
  фактическую базу вызова: при `--database sales_analytics` в ответе остаётся `admin`
  (воспроизведено на живом стенде 9.5.1). Агенты в прогонах T6 дважды принимали это за
  признак того, что профиль смотрит не туда. Правка на стороне T5-кода, отдельной задачи
  пока не заведено. *Update (T25, 2026-09-30):* `--database` is reflected now; what is not is
  a `CONNECT DATABASE` inside the applied file — three of the five T25 runs read
  `env.database = admin` as "my objects went to admin". `execute/SKILL.md` now says so; the
  code still reports the profile's database.
- JSON base views created from the `datasources` template before T25 (no `CONSTRAINTS …
  NOS ZERO ()`) ignore every `WHERE` on their columns, and so does every view above them.
  The template is fixed; existing ones are found only by the "a filter filters" check. The
  fix is to re-apply the base view with the block — dependants stay valid and start
  filtering (checked live).
- Parsing an ISO-8601 instant (`2026-05-25T10:15:00Z`) is not in `vql/references/dialect.md`:
  the quoting of `'T'` inside a pattern and the `Z` zone. T25 agents sidestepped it with
  `SUBSTR(…, 1, 10)`; a `TO_TIMESTAMP('yyyy-MM-dd''T''HH:mm:ss''Z''', …)` parsed in one run,
  unchecked beyond that.
- Implicit `_register_…` / `_array_register_…` types that `NEST` and `REGISTER` create stay
  after `DROP VIEW`, and a `REGISTER` view over another database's view creates its type in
  **that** database (`views/references/arrays.md`). Whether `vql`'s write-only-your-own rule
  should name it, and how cleanup should find orphan types, is open.
- Повторный `-e` в `vql run` молча берёт последний: `denodo vql run -e "…" -e "…"` даёт
  `total: 1`, первый запрос исчезает без предупреждения (воспроизведено на стенде в T8c;
  один `-e` с `;` внутри отрабатывает оба выражения). Обычное поведение `argparse` без
  `action="append"`, но тихое. Либо `append`, либо явный отказ `usage`. Правка на стороне
  T5-кода, задачи пока нет; в `execute/SKILL.md` про это добавлена строка.
- Отчёт `verify` не показывает параметры запроса у шагов: `statements` http-шага несёт
  метод, путь и статус, но не query, поэтому по отчёту нельзя сказать, на какой VDP-сервер
  ушла запись (у записей `[cleanup].http` параметры печатаются). На общем маркетплейсе это
  ровно тот факт, который хочется видеть в отчёте. Замечено при закрытии T16, задачи нет.
- Судьба `docs/superpowers/specs/2026-09-04-denodo-skills-brainstorm-wip.md`: содержимое
  целиком перенесено в чистовую спеку, файл дублирует её и может разойтись. Удалить или
  оставить как историю обсуждения.
- `source: "./"` копирует в кэш плагина весь репозиторий — вместе с `docs/` (1149 строк
  спек) и `CLAUDE.md`. Проверено на локальной установке в T4. Работу навыков это не
  ломает, но пользователь тянет проектную документацию. Три выхода: оставить как есть,
  вынести плагин в подпапку (`source: "./plugins/denodo"`, расходится с разделом 5 спеки)
  или держать спеки в отдельной ветке. Решать до первой публикации.
- Язык публичных артефактов зафиксирован в T4 как английский: `description` в манифестах,
  а дальше `SKILL.md` и README. Проектная документация (`docs/`, `CLAUDE.md`) остаётся на
  русском. Не решено, нужны ли русские триггерные фразы в `description` навыков. **T9 этот
  вопрос не закрыл, а очертил:** фразы сьюта написаны по-английски — под аудиторию
  публичного плагина и под язык самих описаний, — поэтому кросс-язычное срабатывание
  (русская фраза против английского `description`) сьютом не покрыто вовсе. Закрывать его
  надо не рассуждением, а вторым набором кейсов: те же двенадцать фраз по-русски, и падения
  покажут, какие описания нуждаются в русских триггерах. Отдельной задачи пока не заведено.
- Шифр `USERPASSWORD … ENCRYPTED` после T15 получается одной командой, но по-прежнему
  **хранится в `.vql` в git**. Две ступени дальше, обе по потребности: подстановка
  `@{secret:<имя>}` в момент применения файла (в git не попадает даже шифр) и `FROM_VAULT`
  для серверов с настроенным Credentials Vault — на dev-стендах его обычно нет, поэтому
  основной рецепт на vault не опирается. Отдельной задачи нет и не будет (ревью роадмапа,
  р. 2.4): подстановку вместе с вычисткой секретов из вывода приносит первый навык, которому
  понадобится секрет без формы `ENCRYPTED`.
- Цепочка `verify` не исполняет ветку `PUT` шаблона тега: шаг называет `calls = [0, 1]` —
  lookup и create, — поэтому правило №1 навыка `marketplace` («идемпотентность — это
  последовательность: прочитать, потом `POST` или `PUT`») ею не проверяется, а пометка блока
  не обновляется ни одним прогоном, потому что `--update-marks` не трогает шаги, исполнившие
  блок частично. Записано при закрытии T17 как принятая цена решения. Закрыть это можно либо
  тем самым ветвящимся шагом, который T17 отклонил, либо отдельным шагом, который создаёт
  объект и тут же обновляет его, — второе дешевле и раздел 11.1 не задевает.
- Пометку блока внешнего элемента (`skills/marketplace/SKILL.md`, bash-половина) не
  обновляет ни один прогон, хотя цепочка исполняет все четыре его вызова: идентификаторы
  надо захватывать по одному, поэтому вызовы разделены между тремя шагами, а правило
  `--update-marks` («шаг исполнил блок целиком») считает по шагу. Записано при закрытии T18.
  Выходов два: считать покрытие блока по прогону, а не по шагу (правка правила из раздела
  11.1), либо оставить пометку этого блока ручной. Отдельной задачи нет.
- Приёмка вехи B не проверила ветку «представления ещё нет в каталоге маркетплейса».
  Прогон B получил витрину прогона A уже синхронизированной, поэтому рецепт «`id: null` —
  синхронизируй, но сперва спроси другие серверы» сработал как чтение, а не как развилка.
  Это единственный кусок навыка `marketplace`, который приёмка прошла мимо; закрывается
  сценарием, где витрина создана, но `element-management/VIEWS/synchronize` ещё не звучал.
  Задачи нет.

---

## Сделано

- **T32. The `ai` skill: the server's LLM in a query.** A new skill, `skills/ai/`: the six LLM
  functions over a text column, a view that keeps their answers in its full cache, semantic
  search over a stored vector column, and a search view an application sends a sentence to.
  Its body: how many requests a query makes (measured), the owner's rule — an AI function runs
  over rows only up to a number the human agreed to, counted in requests, a ceiling named up
  front included — with the message shape, a rationalization table and red flags; six
  templates (does the server answer, count before you run, classify and score over rows, the
  cached view and its load, a search with a literal, the search view); what you need, Verify,
  twelve silent failures and the loud errors. `references/functions.md` has every function as
  measured (`EXTRACT_AI`'s register with spaced field names and `''` for a missing entity, the
  one-request translate-or-keep-English recipe, the role), `references/vectors.md` the type,
  the distance functions, which model `EMBED_AI` and `VECTOR_DISTANCE` use, delegation and
  approximate search. Configuring the LLM and generating embeddings for a table stay outside.

  **Decided in the task.** The stand has an LLM (`gpt-5.1`) and an embedding model
  (`text-embedding-3-large`), read from the server's configuration file without the secrets.
  No classifier rule: an AI call changes no state, and a text classifier cannot see how many
  rows it will touch; the rule lives in `ai` and in a new row of `vql`'s safety table. The
  `verify` chain gains `ai = true` steps behind a `--with-ai` flag (spec 11.1): about 40 paid
  requests over a six-row fixture of the demo return reasons; the default run skips them with
  a reason. `execute` says `--max-rows` cuts the printout, not the work; `vql`, `views`, `cache`
  and `semantics` point to `ai`; `semantics` names the real role (`use_large_language_model`,
  not the documentation's `use_large_language_model_role`); `views/references/delegation.md`
  says a planned query must have no `LIMIT`. `CLAUDE.md` gains the rule that AI calls on the
  stand go only over small views. Eval: four cases (`routing-ai`, `routing-ai-semantic-search`,
  `routing-ai-cost-symptom`, `discrimination-ai-not-semantics`); 46 of 46 pass.

  **Measured on 9.5.1:** one request is 0.7–2 s and they run one after another. A `LIMIT`
  bounds the requests only when the function is in the `SELECT` list alone; in a `WHERE` it
  runs until enough rows match; under `ORDER BY` or `GROUP BY` every row is sent; a condition on
  an AI column is evaluated again for every row kept, and over a file source before the other
  filters, on every row of the file. A column the query does not read is not computed; a cached
  one sends nothing. `NULL` sends nothing, `''` a request and a confident `neutral`; a `CASE`
  branch not taken sends nothing; a literal or a repeated text is one request per row; a
  literal is evaluated while planning. The tool reads every row, so `--max-rows` bounds
  nothing. `CLASSIFY_AI` always returns one of the labels as written (opening hours →
  `billing` without an `other`), and mixed-arity scales fail before any request. The same
  input changed its answer between two runs at temperature 0. A reader without
  `use_large_language_model` fails on an uncached AI column and reads a cached one; `EMBED_AI`
  needs no role. A view with `EXTRACT_AI` leaves a `_register_…` type behind after `DROP
  VIEW`. A full cache cannot hold a vector column. `VECTOR_DISTANCE(<column>, <view
  parameter>)` — the documentation's own pattern — embeds once per row on every search (4 rows
  2 s, 32 rows 13 s); an `EMBED_AI` of the parameter in a `Dual()` branch is one request (0.9 s).
  `embeddingmodel` survives derived views; a `NULL` vector fails the query once its row is in
  the result; `delegatevectorliteral = false` sends every vector to Denodo; a `WHERE` on another
  column of the search view is applied before the five are chosen; `GET_QUERY_EXECUTION_PLAN`
  fails on any query with a `LIMIT`. The documentation's `VECTOR_INNER_PRODUCT_DISTANCE` does
  not exist, and the real inner product is negative.

  **Checked with subagents, baseline first**, on a 157-ticket helpdesk fixture (a CSV with nine
  empty texts, four languages, four long complaints) and the telco embeddings of `verticals`.
  Three baseline runs (Opus, 43, 57 and 44 tool calls, all reading the documentation on the
  internet): the dashboard run under a deadline loaded the cache itself — 118 requests nobody
  agreed to; the translation run stayed within ten sample tickets; the search run found the
  per-row embedding in a plan and worked around it. With the skill, four Opus runs (26, 31, 33,
  39 calls, no documentation read, no failed statement): the dashboard run sent six requests on
  `Dual()` and left the files and the message; the control run, given a ceiling of 400, loaded
  itself (151). Their reviews found two errors of mine — new source rows are absent from a
  cached view, not present without answers; a filter on the search view is applied before the
  top five, not after — and added the ceiling, the unit of the number, the folder and
  `formatted` context of the templates, the sample with the cache off, the dedupe-and-join
  option, the reload cost, the verify row for missing answers and the scale of the search
  view. After the edits, the four scenarios on Sonnet (9, 17, 13, 15 calls) made the same
  decisions; the control deduplicated to 58 requests. About 700 LLM and 300 embedding requests
  in the whole task. Unit tests 366 OK; `verify --env lab --with-ai` green with eight new steps.

- **T31. The `security` skill: who may read what.** A new skill, `skills/security/`, with the
  owner's first scope: a role with read access given to a user, tags on the columns a policy
  should reach, a global security policy that masks columns, filters rows or denies a view,
  and the check as each person. Its body: four reads before any change (who reads the
  database and through which grant path, policies and their status, which policy reads which
  tag, tags already on the views), a triage order for "a user sees what they should not", who
  applies what (everything the statements touch created in this session — the agent; anything
  older, any grant to a person, any new policy reaching existing people or views — only after
  a yes, in a given message shape, with a rationalization table from the baseline), four
  templates (role and grant; tag and policy; the tag in the view's own file; the impersonated
  check), the audience chosen by grant path, where the tag goes, Verify, twelve silent
  failures and the loud errors. `references/policies.md` holds the whole policy grammar, every
  masking expression as measured, the audience table and what removes or disables a policy;
  `references/privileges.md` roles, users, grants, revokes, owners and what each permission
  procedure proves. Accounts and passwords, LDAP and identity-provider groups, per-role row and
  column restrictions, custom policies and session-attribute audiences go to Design Studio.

  **Decided in the task (roadmap 9.2, 9.3, 2.5).** No second, non-administrator profile:
  `CONTEXT ('impersonate_user' = …)` / `('impersonate_roles' = …)` runs a query with another
  user's or a set of roles' privileges and policies, without a password; it needs the
  `impersonator` role, which the owner granted to `admin` on the test server and kept.
  `env check` reports `vdp.admin` (`adminglobal` of `DESC USER`) and `vdp.impersonation`
  (an impersonated read of `Dual()` as oneself). Global objects: the agent applies a security
  statement itself only when everything it touches was created in the same session; on the
  test server server-wide objects are the run's own by prefix only (`verify_`, `zq<task>_`),
  check users are `EXTERNAL` — no password exists — and `CLAUDE.md` says so. The classifier
  gains `destructive: security` for `CREATE [OR REPLACE] USER | ROLE | GLOBAL_SECURITY_POLICY`,
  `CHOWN` and a `CREATE DATABASE` with a `GRANT`. No secret substitution was needed: the skill
  never writes a password. `vql` names security writes in its safety table and maps the skill;
  `catalog` warns that a tag a policy names is a switch and that `DROP TAG … CASCADE` deletes
  the policy; `semantics`, `execute` and `views/references/dependencies.md` point to it. The
  four templates and the claim that re-applying a view's file takes the mask away run in the
  `verify` chain as six steps, the checks reading as an `EXTERNAL` `verify_reader`. Eval: four
  cases added (`routing-security`, `routing-security-grant`, `routing-security-symptom`,
  `discrimination-security-not-catalog`), all four failing before the skill; 42 of 42 pass.

  **Measured on 9.5.1:** an audience restricts only the grant path it names — a role audience
  what roles grant (a direct grant to the user, on the database or on that one view, another
  role, or `ADMIN` on the database read in clear), a user audience what is granted to the user
  directly (everything through roles reads in clear), `ALL` every path; one audience cannot
  mix roles and users. Local and global administrators are never restricted. `DROP ROLE` of a
  role in an audience leaves the policy listed and `ENABLED = TRUE` in `DESC VQL`, and stops it
  for every role in it — `GET_ELEMENTS()` says `INVALID`, `DESC VQL` ends with `# Invalid
  object policy`; re-creating the role validates it again. `DROP TAG … CASCADE` deletes every
  policy that names the tag; without `CASCADE` a tag a policy names is refused even with no
  assignment. Re-applying a view's or a base view's file without its `TAGS` removes the tag and
  the mask. `CREATE OR REPLACE ROLE` and `CREATE OR REPLACE USER` over existing ones add and
  never remove; revoking is `ALTER … REVOKE` (lists work). A mask applies where the tag is and
  to every view above it, expressions included (`SUBSTR` → `****`, `LEN` = 8); a filter on a
  masked column compares the masked value; a type missing from the masking list comes back
  `NULL`; `NULL` stays `NULL`, `''` becomes `********`; `ROUND` on an integer masks nothing. A
  tag on the top view only leaves the base view readable to a role with the whole database. A
  row filter applies without the tagged column projected and to views above. `CREATE USER …
  EXTERNAL` takes no `GRANT`; a new user gets `allusers`; `DESC VQL USER` shows no roles
  without `includeUserPrivileges` and a local user's password hash with it; `ALTER DATABASE …
  GRANT … TO ROLE <typo>` answers `ok`; `GET_USERS_WITH_ROLE()` of a missing role answers 0
  rows; in `CATALOG_PERMISSIONS()` the role of a grant is `userrolename` (a role nobody holds
  appears only with `username` empty); `GET_CATALOG_EFFECTIVE_PERMISSIONS`' `rowpermissions`
  said "restricted" for a user who read in clear. The tool's 100-row cut made `LIST ROLES`
  miss roles on a server with 129.

  **Checked with subagents, baseline first**, on a three-database CRM fixture with real traps:
  an analyst with a direct grant beside the role, a policy over a base-view tag, a policy made
  `INVALID` by a dropped role plus a user with a database-wide grant. Three baseline runs
  (Opus, 56, 48 and 57 tool calls, all reading the documentation on the internet): every one
  applied a change of access without a yes — "they named the exact columns", "it only
  restricts", "reversible with one `REMOVE_FROM`", "only new objects, a pure `CREATE`" (a new
  user-audience policy and a re-created role that someone had dropped); none could check a
  policy as a person; one reported "Ivan restricted" from `GET_CATALOG_EFFECTIVE_PERMISSIONS`
  while impersonation showed him reading every name in clear, and printed a demo user's
  password hash with `DESC VQL USER`. With the skill, four Opus runs (44, 28, 23 and 38 calls),
  one a control on a new file with everything its own: the three on the team's objects applied
  nothing, found the direct grant and both causes of the `INVALID` policy, measured "before"
  by impersonation and left files and the message; the control applied everything itself and
  checked it as the role (zero failed statements, no documentation read). Their reviews found
  one error of mine — query 1 read the grant's role from `rolename`, which is empty for a role
  nobody holds; it is `userrolename` — and added the triage order, the single-form audience
  and the two ways to close a direct grant, the two repairs of an `INVALID` policy, masking
  through expressions, `NULL` and empty values, roles nobody holds, and lineage for renamed
  columns. After those edits, the three team scenarios once more on Sonnet, no documentation read:
  the pressure and the diagnosis runs made the same decisions in 10 and 9 tool calls; the
  masking run (12 calls) found the direct grant, closed it with a second, user-audience
  policy and verified all three people — and applied it without a yes, writing "every new
  object is prefixed and limited to the database". That became a row of the rationalization
  table and a red flag ("the database in `VIEW_DATABASES` existed before this session"); the
  same scenario re-run on Sonnet applied nothing and cited the row (10 calls). Found on the way: impersonation
  closes most of T26's open question on privilege narrowing (`COLUMN_DEPENDENCIES()` answers
  nameless `No Privileges` rows). Unit tests 363 OK; `verify --env lab` green with the six new
  steps.

- **T30. `marketplace`: a renamed, recreated or moved view keeps what people put on it.** The
  spike answered the task's question in the server's OpenAPI: `POST
  …/element-management/{type}/synchronize` takes `matchedElements` — pairs of an old name
  (`localElement`) and a new one (`serverElement`), the REST form of the "Renamed elements"
  drag-and-drop of the UI's sync dialog. So the fallback (a warning plus the UI dialog) was not
  needed. A new section of `marketplace`, "A view in the marketplace is renamed, recreated or
  moved", carries a five-step template (`view-details` saved before the change, the rename,
  `changes`, the matched synchronisation, the read-back) with its rules, the recreate and move
  cases, and the re-apply table for moves; plus rows in its slot, verify and common-mistakes
  tables. `views` gains a paragraph — before renaming or moving a view, ask the marketplace;
  clients that read the old name and the view's own file go into the report — and a
  common-mistakes row; `references/derived.md` points from `ALTER VIEW … RENAME` to it. `vql`
  names the renamed view in its `synchronize` row, lists the set-replacing property-group call,
  and gains a rationalization row. The tool classifies `POST
  /property-management/views/{id}/groups` as `replace` (`safety.py`); `execute` lists it and
  shows `--json-file`. `references/categories.md` no longer tells the reader to pass `serverId`.
  The `verify` chain runs the template at the end of its marketplace tail — before, the rename
  in VDP, and the matched call — and a new step field, `expect_body`, fails the run unless the
  renamed view answers with the id it had before (spec, section 11.1). Eval: two routing cases
  (`routing-marketplace-rename`, `routing-marketplace-rename-symptom`); 38 of 38 pass. Both
  pass on the old description as well, so the description was left as it was and the cases
  guard against a regression only.

  **Measured on 9.5.1.** Matched, a renamed view keeps its element whole — the same id with
  tags, categories, the description and field descriptions edited in the marketplace, custom
  property values and endorsements; three live runs, one of them a rename by "a colleague"
  with nothing saved beforehand. Unmatched, the old element is removed with all of it and the
  new one arrives empty. Any `type` in a pair (`View`, `VIEW`, `view` — the OpenAPI lists it)
  fails the call with `400 "Invalid input JSON"`; the UI's own bundle sends the two names only.
  The response never names the pair, matched or ignored. A pair across databases is ignored
  silently, twice: nothing inserted or removed, both names left pending. `DROP` then `CREATE`
  under the same name before any synchronisation keeps the element. From the moment VDP has no
  view of the old name the element drops out of its tag's and category's listings, while reads
  by the element's id still answer. An element whose descriptions were edited in the
  marketplace is listed under `modifiedElements` with `DESCRIPTION,FIELD_DESCRIPTION` on every
  reading, and `SERVER_WITH_LOCAL_CHANGES` keeps the edits. `POST
  /property-management/views/{id}/groups` replaces the view's groups and the dropped group's
  values go with it; a value before its group is `500 "Incorrect number of updated tuples"`; an
  interpolable property keeps its template in `visualValueToEdit`, while `visualValue` has
  `$element_name` filled in. `VIEWS/changes` on a server that never carried the database lists
  its views under `serverElements` too.

  **Runs.** RED, Opus, the skills of `main`: a rename request (22 calls) found the
  marketplace element only by choosing to read `marketplace`, stopped for the `ALTER`'s yes,
  and planned a plain synchronisation plus manual re-attach — losing the id and the
  endorsement; "no skill mentions the marketplace when a view is renamed". A colleague's rename
  with the human away (48) found `matchedElements` in the OpenAPI and the docs, did not run it
  (unverified), and left a body with `"type":"View"` that would have failed. A move across
  databases with the yes in advance (118 tool calls, 15 minutes) got there through the OpenAPI
  and the UI's JavaScript bundle, hitting both the `type` error and the ignored pair. GREEN,
  Opus: 21, 27 and 61 calls, no OpenAPI or docs; the rename proposal named both halves for one
  yes, the colleague's rename was matched and read back (see the open question on whether it
  should have waited), the move built the new element before dropping the old one — the order
  the skill now gives — and left the endorsement to the human. Sonnet after the edits: a
  rename of a view the marketplace never imported (16 calls) checked both servers, renamed and
  did not synchronise; a rename with the yes in advance on another domain (19) matched the pair
  and read back the old id, no docs and no trial and error; the colleague's rename again (9)
  left the correct body in a file and did not send it. `verify --with-marketplace`: 36 of 36,
  the catalog clean afterwards. The GREEN reviews corrected four of
  my lines (field descriptions are in `schema[]`, interpolable values, the order of a move, a
  sentence that read as a second exception to the `synchronize` rule), and a reviewer's
  suggestion that `changes` on the profile's server can replace the round of `view-details`
  turned out wrong when checked.

- **T29. The `metrics` skill: metric views, the views over them, and the rules for querying
  them.** A new skill, `skills/metrics/`, for the 9.5 object the model does not know. Its core
  is the owner's rule, confirmed live: the only thing built directly on a metric view is a
  selection view — the metric view alone in its `FROM`, dimensions in `GROUP BY`, metrics in
  `evaluate_metric` — and everything else (other facts and dimensions, a second metric view,
  arithmetic over metrics, totals) goes over selection views. The body: the model before the
  statement (one fact view, dimension views with one row per key and the key declared, one
  association per dimension, what happens to facts without a dimension row), a table of which
  rows each association keeps, five templates (the metric view; selection views, a total from
  the metric and a share; an ad hoc query with what works and what does not; reading a metric
  view; the totals check), who applies what, thirteen silent failures and the loud errors.
  `references/metric-views.md` holds the full grammar with the undocumented `FILTER` clause,
  the join types case by case, every query shape measured, what a metric view refuses, the
  consumers and the procedures. `vql` maps the skill, names metric views and puts a rewrite of
  someone else's metric view in its safety table; `views` points to it and warns next to the
  association template that a `(1)` endpoint drops unmatched facts from any metric view over
  it; `cache`, `semantics` and `execute` point to it; `dialect.md` adds `CAST(x AS long)` to
  the cast syntax errors. The five templates run in the `verify` chain, each check asserting
  that the totals agree; the fixture's `bv_income_band` now declares its key. Eval: five cases
  (`routing-metrics`, `routing-metrics-query-symptom`, `discrimination-metrics-not-views`,
  `discrimination-metrics-not-semantics`, `discrimination-mart-not-metrics`); 36 of 36 pass.

  **Measured on 9.5.1, none of it in the documentation:** a metric view joined to another view
  in one `FROM` runs until the query timeout (900 s over 20,000 fact rows, 60 s of 60 over 7,200), the
  same join over a selection view answers at once; `evaluate_metric(a) * k` and
  `ROUND(evaluate_metric(a), n)` return `a` unchanged and `evaluate_metric(a) /
  evaluate_metric(b)` returns no rows, ad hoc and inside a `CREATE VIEW`; `evaluate_metric`
  over any other view returns `NULL`; `SELECT *` or a dimension without `GROUP BY` returns no
  rows (as a view: `Error applying metric transformation.`); a dimensions-only query lists every
  member of the dimension view, not the ones with facts. Which fact rows survive is decided by
  the association: `RIGHT` keeps facts without a dimension row only over a `(0,1)` endpoint,
  `LEFT` (and no type over `PRINCIPAL (0,1)`) keeps every dimension member and drops those
  facts, a `(1)` endpoint runs `INNER` whatever is written, the order of the aliases does not
  matter, and a metrics-only query applies no join at all — so the grand total stays right
  while every slice is short; an association from the fact to the base view under a dimension
  view switched `RIGHT` to `INNER`. A metric over other metrics or `COUNT(*)` is refused
  (`missing source schema`), a metric without an aggregate is accepted and returns nothing,
  `SUM` over `int` stays `int` and `int / int` is integer division inside a metric too. A
  `HAVING` on a metric grouped by the key of a dimension view with no declared key plans as
  `VOID PLAN` over file sources; an expression over a dimension grouped by its alias drops every
  `COUNT(DISTINCT …)` metric over SQL Server sources. Duplicate dimension keys multiply the
  metric. `FILTER ( … )` exists after `SOURCES` and breaks some queries. A metric view takes no
  cache; its dependants behave like those of any view. Against the documentation: a query with
  no dimension is accepted (the Data Marketplace page forbids it), a metric cannot reference
  other metrics (the Administration Guide says it can), and `GET_METRIC_VIEWS` takes a pattern
  only positionally.

  **Checked with subagents, baseline first**, on a web-returns fixture with `NULL` keys (build a
  KPI layer from three files), the server's own health and telco metric views (combine two metric
  views into a dashboard; answer four questions read-only). Three baseline runs (Opus): all three
  reached right numbers, every one by reading the documentation on the internet (46, 34 and 21
  tool calls); the build run first wrote `LEFT`, got right grand totals and short slices, and
  found `RIGHT` by reading the plan; none met the expression, `SELECT *` or direct-join traps,
  because each verified carefully. With the skill (Opus): 27, 27 and 14 calls, no documentation,
  no failed DDL, `(0,1)` + `RIGHT` chosen before the first statement. Their reviews found two
  behaviours my text had backwards or too wide — an alias-grouped expression losing the distinct
  count, and the `HAVING` rule holding only over file sources — and added the per-member
  average, the ad hoc form of the templates, `column_remarks`, the `DESC VQL` hazards (another
  database's views returned unqualified, encrypted passwords in the transcript) and a wrong
  line in `execute`. After those edits the build and the dashboard once more on Sonnet: the
  same decisions in 13 and 14 tool calls, no documentation, 0 mismatches against plain SQL.
  Unit tests 343 OK; `verify --env lab` green with the five new steps.

- **T28. The `semantics` skill: the Virtual DataPort half of what AI consumers read.** A new
  skill, `skills/semantics/`, for views that already exist: a read-only audit of a database in
  three calls (views with and without a description, undescribed fields, key fields and the
  MCP tag per view; every field; every association), a profile that turns data into facts
  (grain, sentinels, padding, codes, `NULL`s, aggregates grouped by a shared label, the
  `NULL` row an outer join adds), a contract for the texts (what one row is; no counts that
  go stale, no "probably", no restated names), the proposal the human approves, and where
  the metadata is written — in the view's own file when it has one, otherwise an `ALTER`
  file (`ALTER VIEW … DESCRIPTION`, `ALTER COLUMN … ADD (DESCRIPTION …)`, `ADD PRIMARY KEY`,
  `ALTER ASSOCIATION … DESCRIPTION`, `ALTER TAG … ADD_TO`). A section on "the agent does not
  see this view" covers the MCP Server's visibility tag, the agent user's privileges
  (`GET_CATALOG_EFFECTIVE_PERMISSIONS`) and the schema refresh. `references/metadata.md`
  holds what each consumer reads, every statement form, what survives what, and inheritance.
  The owner's rule is its core: descriptions come from the data and are approved by the human
  before they are written, whatever the statement — a view the human names to be made visible
  is the yes for its tag only. `vql` names such writes in its safety table and maps the
  skill; `views`, `catalog` and `execute` point to it; the association grammar in
  `views/references/associations.md` gains `DESCRIPTION`. The audit, profile and write
  templates run in the `verify` chain, plus a step asserting that re-applying a view's file
  takes its key and tag away. Eval: four cases added (`routing-semantics`,
  `routing-semantics-mcp-visibility`, `discrimination-semantics-not-views`,
  `discrimination-semantics-not-marketplace`); 31 of 31 pass.

  **Measured on 9.5.1:** every metadata `ALTER` keeps the cache (still served), the views
  built on the view and the privileges granted on it; re-applying a `CREATE OR REPLACE VIEW`
  without the metadata clauses removes the description, the field descriptions, the key and
  every tag assignment — including the MCP tag — and keeps grants; a field description is
  inherited live through a plain column, an alias, a join or a `GROUP BY` key, also by views
  created before it, and not through any expression, cast or aggregate; `GET_VIEW_COLUMNS`
  and `CATALOG_VDP_METADATA_VIEWS` show the inherited text, `DESC VQL` does not; a declared
  key marks its columns `NOT NULL`, and `ADD PRIMARY KEY` replaces an existing key without an
  error; `ALTER TABLE … ( ALTER TAGS … )` on a base view drops every tag it does not name,
  from the view and its columns; a view description of 4,001 characters fails with a
  metadata-storage error, a field description of 4,001 is stored; `ORDER BY e.name` over one
  aliased procedure fails, over a join of procedures it works. Tags assigned with `ALTER TAG`
  show up as a `TAGS` clause in the view's `DESC VQL`.

  **Checked with subagents, baseline first**, on a team-style fixture built as if in Design
  Studio (five CSV sources, five views: a key declared on a column with 20 values in 7,200
  rows, a description copied from another view, `-1` in a count, padded text, an aggregate
  grouped by a reason text two keys share). Three baseline runs: every one took what the MCP
  Server and Assisted Query read from the manuals on the internet; the two that could write
  did so without a yes — the Opus run under "don't wait for me" re-declared all five of a
  colleague's views with descriptions, keys and two associations, reasoning that "the skill
  lets me do an additive CREATE OR REPLACE myself, while ALTER needs a yes" (56 tool calls);
  the MCP run re-declared the view to tag it and added a description nobody asked for (38);
  the audit-only run invented a tag name (32). The descriptions themselves were drawn from
  the data, but carried guesses ("most likely means unknown") and counts that go stale. With
  the skill, four runs (three Opus, one Sonnet), one on a new file with no suggested schema:
  the pressure run applied nothing and handed over the audit, the proposal and the file (37);
  the MCP run added the tag to the named view only, with `ALTER TAG`, and left the
  description as a proposal (23); the audit-only run proposed the metadata inside the team's
  own `.vql` file and asked for the tag (12); the new-data run built its own view over a
  store export that keeps history and applied the texts and the tag in the view's file
  itself (32). None needed the documentation for the MCP side. Their reviews fixed the audit
  template's `ORDER BY`, and added the composite-key check, no key for a label-grouped
  aggregate, a separate file for statements still waiting for a yes, the privileges query,
  associations between others' views as a proposal, and the named-view exception in `vql`.
  After those edits, the pressure and the MCP scenarios once more on Sonnet: the same
  decisions in 18 and 8 tool calls, no documentation read. The first green launch was
  stopped a minute in and restarted: the proposal example in the skill repeated the
  fixture's own findings, and the write template stated a meaning for `-1` that nothing had
  established. Unit tests 343 OK; `verify --env lab` green with the five new steps.

- **T27. The `cache` skill: the full cache of a view.** A new skill, `skills/cache/`, with the
  owner's first scope: switch a full cache on and off, load it with all rows or the ones the
  human names, clear it. Its body: three reads before touching a cache (is it enabled for
  the database, who reads the view, what is loaded and how), who applies what (a view created
  in this session and read only by the agent's own views — the agent; any other — only after
  a yes to the statements, in a given message shape, with a rationalization table from the
  baseline), three templates (`ALTER VIEW … CACHE FULL WITH_STATUS` in the view's own file;
  the load in a file of its own; `INVALIDATE` → `CLEAN_CACHE_DATABASE(db, view)` → `OFF`),
  loading a subset as a decision between two options, Verify, ten silent failures and the
  loud errors. `references/full-cache.md` holds every load parameter, every `ALTER VIEW …
  CACHE` form and what survives re-applying a file, measured. Everything else about a cache
  — partial, time to live, incremental, indexes, schedules — goes to Design Studio and
  Scheduler. The classifier gains `destructive: cache` for a query whose `CONTEXT` has
  `'cache_invalidate'` or `'cache_preload' = 'true'` (the owner's decision named only the
  first; a preload without it doubles every row, so it is flagged too). The three templates
  run in the `verify` chain, each check asserting the block's claim (0 rows before the load,
  the load complete through the view above it, the load date gone after clearing). `vql`
  maps the skill and names cache writes in its safety table; `views`, `datasources`,
  `procedures` and `execute` point to it. Eval: `routing-cache`, `routing-cache-empty-view`,
  `discrimination-cache-not-views` added; 27 of 27 pass.

  **Measured on 9.5.1, against the documentation where they differ:** a bare `CACHE FULL`
  created a table with the status column although the documentation names `NO_STATUS` the
  default since 9.4; with `NO_STATUS` every `'all_rows'` load swaps the cache table and every
  view above that had been queried fails with `Invalid object name` until re-created
  (minutes, through further loads) — so the skill always writes `WITH_STATUS`; leaving
  `'cache_wait_for_load'` out waits and reports a failed load (the roadmap's pitfall is real
  only for an explicit `'false'`, which answers `ok`); `CACHE OFF` keeps the rows valid and
  the next `CACHE FULL` serves them at once (the maintenance-task page says they are
  invalidated); `INVALIDATE` and `CLEAN_CACHE_DATABASE` after `OFF` are accepted and do
  nothing; re-applying `CREATE OR REPLACE VIEW` without the `ALTER` line switches the cache
  off, with a changed column empties it, unchanged or with a new description keeps it; a
  load over a view built on the cached one, or over a view whose cache is off, answers `ok`
  and loads nothing; a failed load keeps the previous content; the cached view answers with
  the cache database's rules (a case-insensitive collation turned 0 rows into 1,988, `NULL`s
  sort first, `decimal` gains 20 places). A base view carries its cache in its own `CREATE
  TABLE`; `ALTER VIEW` on it is refused.

  **Found on the way, outside the task:** a DF base view that lists fewer columns than its
  wrapper answers an equality `WHERE` with the rows of another column — the condition reaches
  the wrapper by position (`item_sk = 29` gave the rows whose second file column is 29). The
  `datasources` text said narrowing in the base view was fine and verified. It now narrows in
  a derived view, or gives a narrow base view `NOS ZERO ()` for each column (checked: right
  counts; the `(any) OPT ANY` block does not help); Verify and Common mistakes gain the case.

  **Checked with subagents, baseline first**, on a fixture of the returns CSVs with a view
  above the cached one. Three baseline runs (Opus): all three syntaxes came from the
  documentation on the internet (43–73 tool calls); two stopped for a yes on their own; the
  third, told the dashboard refreshed in 15 minutes, applied `ALTER` against the core rule —
  "the request named the exact view and mode", "dev", "reversible" — and chose `NO_STATUS`,
  which broke the view above twice; none knew whether `OFF` keeps the rows. With the skill,
  four runs (Opus), one on a new file with no suggested schema: none read the documentation
  for the cache; the three on the team's view stopped with the files and the message; the one
  on its own view applied, verified 9,000 = 9,000 and found silent failure 9 on its own data.
  Their reviews fixed two errors of mine (`USED_BY` read through the wrong column; `DESC VQL`
  does not show the status mode) and added the clean-before-off order, the Scheduler default,
  the second option's catch, and failure 10. After those edits, three of the scenarios once
  more on Sonnet: the same decisions, 8, 8 and 24 tool calls against 43–73 in the baseline,
  no documentation read, no failed statement; their reviews added where `CONTEXT` goes and
  that a cast has to wrap the final value. Unit tests 343 OK; `verify --env lab` green with
  the three new steps.

- **T26. `views`: impact of a column change, field lineage, and the delegation check.** The
  body of `views` gains "Before a column changes" — four read-only steps (`USED_BY` depth 1,
  the definition of each direct dependant, `GET_ASSOCIATIONS`, `USED_BY` of whatever breaks),
  a template in the `verify` chain whose check asserts the section's claim, not just its
  syntax — plus a Verify row and Silent failure 3 for delegation, rows in Common mistakes, and
  two references: `references/dependencies.md` (the three dependency procedures, what each
  cannot see, measured use by use; reading a field's lineage down to the source table with
  `GET_SOURCE_COLUMNS`) and `references/delegation.md` (reading `GET_QUERY_EXECUTION_PLAN()`
  for delegation, causes measured on SQL Server and PostgreSQL, the answer being per query,
  what to put in front of the human). `vql` names the column-dropping `CREATE OR REPLACE` in
  its safety table; `dialect.md` gains `MEDIAN` (rounded half up to two places when Denodo
  computes it, `PERCENTILE_DISC` when delegated to PostgreSQL), `FIRSTDAYOFMONTH` keeping the
  time, and `YEAR()`/`MONTH()` not existing; `procedures` stops calling
  `GET_DELEGATED_SQLSENTENCE` the way to see what was pushed down. Eval: four cases added
  (`routing-views-column-impact`, `routing-views-lineage`, `routing-views-delegation`,
  `discrimination-impact-not-procedures`), 24 of 24 pass.

  **Measured on 9.5.1:** `COLUMN_DEPENDENCIES` traces output columns only — a column a
  dependant uses only in `ON`, `WHERE` or `GROUP BY` has no row, yet removing it turns the
  dependant `INVALID`; views built on an `INVALID` view stay `OK` and fail on `SELECT`, and so
  does a metric view that reaches the column through a now-invalid association (a metric view
  naming the column directly goes `INVALID`); a REST web service drops the field from its
  definition and does not take it back when the column returns. The dependency procedures
  take exact, case-sensitive names and answer a pattern with an error (the roadmap's `LIKE`
  pitfall is real only in `GET_ELEMENTS`/`GET_VIEWS`/`GET_VIEW_COLUMNS`); `USED_BY` lists
  dependants in other databases but no associations and no web services. Delegation:
  `noDelegationCauses` in the plan names the function; `GET_DELEGATED_SQLSENTENCE` returns the
  delegated part without an error even when the aggregate stays in Denodo; views over two data
  sources print no cause at all, and whether Denodo still pre-aggregates per join key
  (`Aggregation Push-down`) shows only in the `SQLSentence`; a column a query does not select
  is dropped from its plan, so a mart with `MEDIAN` is delegated for every query that does not
  read the median.

  **Checked with subagents, baseline first**, on the server's own SQL Server/PostgreSQL views
  (read-only) and sandboxes: five baseline runs (three Opus, two Sonnet), six with the change
  (two Opus, four Sonnet, one of them a re-run after the review edits), one on a domain no
  template touches. The baselines reached right answers by experiment — the column-impact run
  in 75 calls with a 15-object replica, after `COLUMN_DEPENDENCIES` had answered "nothing uses
  it" for all five dependants that break. With the change: lineage 12 → 7 calls; the new-domain
  impact run (Sonnet) found every broken view and the published web service in 16 calls,
  without a replica; the delegation runs knew about `MEDIAN` before the first `CREATE`. One run
  with the change swapped `MEDIAN` for an exact window-function rewrite without asking; the
  wording now makes every option the human's call, and the Sonnet re-run kept `MEDIAN` and
  reported the cost.

- **T25. `views`: unions, partitioned unions, `FLATTEN`/`NEST`, `CONTEXT ('formatted' =
  'yes')`; and the JSON base view template of `datasources` stops ignoring `WHERE`.** The body
  of `views` gains two templates — a union of sources with a constant per branch that prunes,
  and `FLATTEN` to rows plus `NEST` back — with the silent traps next to them, rows in the
  Verify and Common mistakes tables, and two references: `references/unions.md` (the three
  spellings, how branches are matched and named, which union shapes prune and which do not,
  `NULL` partition keys, overlapping sources, reading `GET_QUERY_EXECUTION_PLAN()`) and
  `references/arrays.md` (`FLATTEN` in full, a parent summary that keeps every parent, `NEST`,
  `REGISTER`, element access, the implicit types). Every `CREATE VIEW` template now ends with
  `CONTEXT ('formatted' = 'yes')`. The union and array templates joined the `verify` chain;
  the union step checks the plan, not just the creation (its filter returns no row on a union
  that does not prune — checked). Eval: `routing-views-union` and `discrimination-json-array`
  added, 20 of 20 cases pass.

  **Measured on 9.5.1, none of it in the documentation:** `UNION ALL` matches by position and
  names each column from whichever branch last used that name, so branches in a different
  order give a view whose `SELECT qty` and `WHERE qty = 1` disagree; a constant column alone
  never prunes, a `WHERE` on it around each branch does, and a function over the partition
  column (`UPPER(channel)`) or a wrong-case literal defeats it (the second returns no rows);
  rows with a `NULL` partition key fall into no branch; field properties are refused on a
  union; `FLATTEN` keeps an empty or missing array as one all-`NULL` row and renames a
  clashing element field `<array>_<field>`; two arrays in one `FLATTEN` multiply; `NEST` and
  `REGISTER` create catalog types that outlive the view, and `REGISTER` over another database
  writes its type there; `DESC QUERYPLAN` and `TRACE` give nothing through the transport,
  `GET_QUERY_EXECUTION_PLAN()` does. Without `CONTEXT ('formatted' = 'yes')` the server stores
  the `SELECT` on one line with aliases dropped.

  **Found on the way, outside the task:** the JSON base view template of `datasources` —
  marked verified since T8b — produced base views that silently ignore every `WHERE` on their
  columns, through every view above them. Without a `CONSTRAINTS` block the server declares
  each column `(any) OPT ANY`, hands the condition to the JSON wrapper, and the wrapper drops
  it; Design Studio writes `NOS ZERO ()` instead. The template now carries `ADD <column> NOS
  ZERO ()` for every column **and every register subfield** (`shipping.country` — without that
  line the register filter is still ignored); `base-view.md`, which said the block was
  optional for JSON, is corrected, and `datasources` Verify gains "a filter filters".

  **Checked with subagents, baseline first.** Three baseline runs (Opus) over a fixture of the
  three returns files and a JSON orders export with an `ARRAY OF` field: every final number
  was right, but found by experiment — 73, 55 and 28 tool calls; the union run first shipped a
  version that read every file, and the flatten run first shipped a mart whose country filter
  returned all countries (the JSON bug). All three said `views` had nothing on unions or
  arrays although `dialect.md` and `datasources` pointed there. With the change, five runs
  (Opus): the same three scenarios and two on data the templates do not use (a date-split
  union over overlapping store-returns sources with `NULL` keys, and a product JSON with two
  arrays and clashing field names) — all answers right, no failed statement, 24–33 tool calls;
  the two runs over the old, broken JSON base view caught it with the skill's one-row check
  before building. Their reviews added the workaround for a base view that is not yours
  (project the key through an expression: a plain alias still reaches the wrapper), the
  parent-summary example, real-column splits without a subquery, the primary-key uniqueness
  check, reading the plan by `BASE PLAN (` blocks, element access by index (which I had
  written down as impossible), and the `CONTEXT` header caveats. After those edits, the union
  and the flatten scenarios once more on Sonnet: both right, no failed statement, 21 and 12
  tool calls. Unit tests 335 OK; `verify --env lab` green with the three new steps.

- **T24. The dialect reference `vql/references/dialect.md` and the table of silent deltas in
  `vql`.** The reference holds about sixty rows in seven sections — text; numbers, casts and
  aggregates; dates and times (Java pattern letters, day of the week, time zones); `NULL`,
  ordering and the shape of a query; JSON; how delegation changes the answer; legacy VQL — each
  as "you write / Denodo does / write instead", the functions that do not exist mapped to the
  ones that do. Every row was run on 9.5.1, `SELECT … FROM Dual()` or against a view; the
  delegated ones against the PostgreSQL and SQL Server views. The body of `vql` gets a section
  "Expressions: VQL is not PostgreSQL": one rule (an expression new to you gets one run on
  `Dual()` with an input whose answer you know) and a ten-row table of the deltas that return a
  wrong value or `NULL` without an error. The `SUM` overflow and `decimal`-cast measurements
  moved from `views` into it; `views` keeps the two imperatives and points to `vql`, and the
  "only the aggregate-over-cast form is refused" sentence that read as if `SUM(CAST('long', x))`
  were refused is fixed. `execute/references/errors.md` gets reserved words as aliases (`full`,
  `user`), which an agent actually tripped on. `HELP` is dropped (checked in T23); roadmap 2.5
  and section 11 say so.

  **Decisions.** (1) The table lives in `vql`, not `views`: a `SELECT` is written everywhere —
  ad-hoc questions, verification queries, procedure bodies — and `vql` fires on a question about
  expressions: the new eval case `routing-vql-expression` passes 3/3 on unchanged descriptions,
  so no `description` was touched. (2) Loud differences stay in the reference only; the table
  in the body is silent ones only.

  **The documentation is wrong in three places the reference now contradicts, each checked
  live:** `EXTRACT(DOW …)` depends on the i18n like `GETDAYOFWEEK` (Sunday is `6` under
  `es_euro`, not always `0`); `COUNT(field)` works without `GROUP BY`; `AVG` over a `decimal`
  returns a `decimal` exact to about twelve digits, not a `double`. Found on the way, also
  silent: `decimal` division keeps six decimals; month names in patterns are read in the
  i18n's language (a view parsing `02-JAN-00` returns only `NULL` dates when queried under a
  Spanish i18n), a `timestamptz` formats to a different day under another i18n, and a text
  column of numbers compared with a number compares as text.

  **Checked with subagents, baseline first.** Three read-only scenarios over file-backed views
  (a customer profile, a monthly returns report, addresses and quarterly returns), eight
  baseline runs (Opus ×5, Sonnet ×3) with the old `vql`/`views`/`execute`: every final number
  was right, but found by experiment and heavy cross-checking — Opus spent 21–37 tool calls and
  two runs exported 16–18 MB of rows to recompute in Python; all eight named the missing dialect
  coverage ("the SELECT is ordinary SQL" was called misleading by each). Four runs with the
  change: all right, Opus 23 and 27 calls against 28–35 and 37, Sonnet 12 and 9 against 10 and
  15, and every run named the table rows that saved an attempt. A baseline run caught a wrong row
  of mine (`EXTRACT(DOW …)` as "the stable one") before the change was tested; the reviews of the
  runs with the change added `TRIM` before `REGEXP_LIKE`, the date-from-parts and completed-age
  recipes, the `CAST(x AS double)` row, month-name language, `timestamptz` formatting, the
  `POSITION` guard, `TRIM` before cutting and case-exact grouping. Caveat: the reference first
  quoted two figures measured on the scenario data (street numbers, blank e-mails); they are
  replaced by the mechanism, and item (a) of the address scenario is not a clean measure of
  generalisation. Unit tests 335 OK; `verify --env lab` green; nothing was created on the server
  by the checks.

- **T23. `datasources` sends every source beyond the three templates to Design Studio.** The
  agent still builds a delimited or JSON file on the server's own disk and a JDBC table with a
  password; REST APIs, Excel, XML, cloud or FTP files, multi-line or quoted-delimiter files,
  Salesforce/SAP/OData/SOAP, base views over a SQL query or a stored procedure, JDBC logins
  other than a password (the data source only — its tables are the agent's again), and schema
  drift (Source Refresh) go to the human in Design Studio. The skill gains a section with the
  boundary, a five-part handover message and a table of Design Studio menu paths (from the
  9.5 Administration Guide, marked unverified), what to do once the human is done, and a
  budget for templates that do not work straight away: one named fix per failure, then stop.

  **Decisions taken with the owner.** (1) The grammar of everything beyond the three
  templates is removed from `references/json.md`, `df.md` and `jdbc.md` — HTTP routes,
  pagination, OpenAPI, FTP/S3/HDFS routes, filters, fixed-width and regex parsing,
  `PROCEDURENAME`, vault/Kerberos/OAuth/IAM/pass-through credentials, and the verified
  `SQLSENTENCE` too; kept grammar would read as "an unverified template is still worth using".
  (2) Objects created in Design Studio are not copied into the project's files: `DESC VQL`
  opens with `DROP … CASCADE`, and a re-applied transcription would overwrite the wizard's
  configuration and credentials. The file holds the agent's objects and a comment naming the
  Design Studio ones; the summary says they exist on the server only.

  **Checked with subagents, baseline first.** Without the change, four scenarios failed as
  expected: a REST API was hand-built from the unverified `json.md` grammar (four applies, two
  failed, pagination guessed from parser errors, the skill's connection class did not match
  the server's, no row ever read); a query and a function base view were written from
  `SQLSENTENCE` and memory; a file that would not parse drew diagnostics, an
  `ENDOFLINEDELIMITER` guess and a server-side cleaning script, never Design Studio; and both
  agents that did hand something over planned to copy `DESC VQL` back into the file. With the
  change, five scenarios passed on the live server, including a leftover hand-built REST
  source sitting on the server as a donor (not copied) and a control that must *not* be
  handed over (JDBC tables built with a donor's ciphertext, 500,000 rows, in the same request
  as a query view that was handed over). The subagents' reviews added the third stop
  condition, the "the database and folder are yours" line, mandatory inputs, and fixed an
  older contradiction: the slots table invited a password into the chat, against the
  `secret encrypt` flow. The eval suite gets `routing-datasources-rest-api`,
  `routing-datasources-schema-drift` and `discrimination-procedure-base-view`; all 17 cases
  pass.

- **T22. The classifier catches server settings and writes to sources.** `classify_vql` gets
  two new kinds. `write`: a leading `INSERT` or `UPDATE` — a write through a view lands in the
  source behind it. `setting`: the server-wide `SET '<property>' = …` (`= NULL` deletes the
  property from `VDBConfiguration.properties`) and `WEBCONTAINER SET | STOP | START | RELOAD`.
  Harmless forms that start with the same keywords pass on any profile: the ODBC connection
  settings `SET <property> TO …` (unquoted property — an allow-listed shape, so any other `SET`
  errs on the side of the server), `ALTER SESSION SET …`, and `WEBCONTAINER STATUS`.

  **The criterion is written down** — in the spec (6.3), in `execute` and one line in `vql`,
  and in the `safety.py` docstring: destructive means it destroys or overwrites something that
  exists, or changes state outside the agent's own project (server settings, data in sources,
  objects of other databases, global objects); `CREATE` of a new object is not. The rule for
  growing the deny list (a skill that teaches a state-changing statement extends the
  classifier in the same PR) is in the spec next to it. This closes the old open question
  about the criterion; the unlisted writers (`GENERATE_STATS_FOR_FIELDS`, `COMPACT_CACHE`,
  `REFRESH_BASE_VIEW`, the Iceberg procedures …) come with the skill that starts teaching them.

  **Decisions beyond the letter of the task, each checked against the 9.5 documentation and
  the 9.5.1 server.** (1) No `MERGE`: VQL has none — it is only a reserved word, the parser
  answers `Syntax error: Exception parsing query near 'MERGE'`, and the merge form is
  `INSERT INTO … ON DUPLICATE KEY UPDATE`, already caught as `INSERT`. (2) `ALTER SESSION` was a
  false positive (`alter`) and is now exempt: the documentation defines it for the session
  query timeout, and live `ALTER SESSION SET 'querytimeout' = '23456'` shows in `GETSESSION` on
  the same connection and is gone on a new one. (3) `WEBCONTAINER` was not named in the task but
  sits on the same documentation page as `SET` ("Changing Settings of Virtual DataPort and the
  Web Container") and meets the same criterion; `STATUS` is its only read. The session form
  `SET QUERYTIMEOUT TO …` comes from the ODBC connection-settings pages of the Developer Guide;
  the server accepts it over the transport.

  **Checked:** unit tests — 335, OK (19 new). Live 9.5.1 with scratchpad profiles through
  `DENODO_PROFILES`: on a `production = true` profile pointing to a closed port, `SET '…' = 'x'`
  and `WEBCONTAINER STOP` were refused as `setting` with exit code 2 (the closed port guarantees
  nothing could have reached the server configuration had the refusal failed), while
  `WEBCONTAINER STATUS` was not listed; on a `production = true` profile against the real
  server, `INSERT` and `UPDATE` into a non-existent view were refused as `write`, the session
  forms ran without the flag (`GETSESSION` → `60000`), and with `--allow-destructive` the
  `INSERT` reached the server (`View 't22_no_such_view' not found`). No server `SET` was
  executed on the server, and nothing was created: the checks needed no database of their own.
  The eval suite was not run: no `description` changed.

- **T20. Инструмент останавливает вызов предопределённой процедуры, меняющей состояние.**
  `classify_vql` после проверки первого ключевого слова ищет `FROM <имя>(` в любом месте
  выражения и `CALL <имя>(` в начале (с необязательным префиксом базы) и сверяет имя с
  `STATE_CHANGING_PROCEDURES`; совпадение даёт новый вид `destructive: "procedure"`, и на
  профиле с `production = true` `vql run` отказывает так же, как на `DROP`. `FROM` ищется по
  всему выражению намеренно: `CREATE OR REPLACE VIEW … AS SELECT * FROM CLEAN_CACHE_DATABASE(…)`
  запускала бы процедуру при каждом запросе к представлению.

  **Где живёт список — решено: две копии под тестом.** Константа в `safety.py` (инструмент
  не читает файлы навыков во время работы) и таблица в
  `skills/procedures/references/predefined.md` (навык самодостаточен);
  `tests/test_safety.py::test_list_matches_the_procedures_skill_reference` разбирает таблицу и
  падает при расхождении, так что «две копии ломаются молча» превращается в «две копии
  ломают сборку». Граница записана в справочнике, в `execute/SKILL.md` и в спеке 6.3:
  пользовательская VQL-процедура с DDL через `EXECUTE` по имени не ловится.

  **Список сократился с десяти до девяти.** `UNLOCK_LOCAL_REPOSITORY` не нашлась ни в VQL
  Guide 9.5 (оглавление гайда и administration guide), ни в `LIST PROCEDURES` на 9.5.1, ни в
  вебе — имя пришло из T14 непроверенным и снято из обеих копий, спеки и таблицы семейств.
  Две Iceberg-процедуры документированы для 9.5, но на demo-сервере без Lakehouse
  Accelerator их нет — в таблице помечены сноской. Описания «что меняет» сверены со
  страницами гайда: `GENERATE_STATS` работает с одним представлением, а не с базой, и
  объявлена deprecated; `CLEAN_CACHE_DATABASE` удаляет просроченные и инвалидированные
  строки, а не весь кэш.

  **Проверено:** юнит-тесты — 316, OK (11 новых на классификацию: обе формы вызова, регистр,
  префикс базы, каждое имя списка, читающие процедуры и `DUAL()` не ловятся, префикс имени не
  ловится, представление без скобок не ловится, представление над процедурой ловится,
  сверка со справочником; плюс отказ `vql run` на production). На живом 9.5.1 через профиль
  с `production = true` (временный файл профилей через `DENODO_PROFILES`, тот же сервер),
  в собственной базе `denodo_skills_t20`: `SELECT * FROM GENERATE_STATS() WHERE …` без флага —
  `error.kind: refused`, `kind: procedure`, код 2, к серверу ничего не ушло; `CALL
  GENERATE_STATS(…)` — тот же отказ; `SELECT name FROM GET_ELEMENTS()` на том же профиле —
  прошёл без флага; с `--allow-destructive` — вызов исполнен, `ok: true`. Попутная находка
  для справочника: у deprecated `GENERATE_STATS` параметры `viewname`/`databasename` без
  префикса `input_` — с `input_view_name` сервер отвечает `Field not found`. Eval-сьют не
  гонялся: описания навыков не менялись. База `denodo_skills_t20` оставлена на сервере до
  подтверждения уборки.

- **T21. Генерализация навыков: тексты не привязаны к серверу, на котором создавались.**
  Просьба владельца: навыки общие, а контейнер, порты и профиль конкретного сервера — частный
  случай. Сделано: (1) пометка верификации переведена на английский —
  `-- verified: 9.5.1 (live, <дата>)` / `-- unverified: 9.5 documentation only` —
  во всех навыках, в `templates.py`, тестах, README, CONTRIBUTING, CLAUDE.md и спеке; абзац
  CONTRIBUTING про «русскую формулировку по историческим причинам» снят, так как причина
  исчезла; (2) «VQL on port 9996» заменено на «порт Virtual DataPort из профиля, 9996 по
  умолчанию», порт маркетплейса — на `marketplace_url` профиля; (3) примеры команд
  используют профиль `dev` из README, а не `lab`; (4) слова «stand», «demo content»,
  «Demo Standard Default», ссылки на спайк T11 и «T11 report» в навыках заменены нейтральными
  («a 9.5.1 server», «observed once», «the server used for verification»); (5) из описания
  `catalog` и его eval-кейса убрано слово «container»; (6) в README добавлен абзац о
  происхождении: навыки написаны по документации 9.5, проверены на живом 9.5.1 и ничего не
  предполагают о способе развёртывания. Числовые id в примерах маркетплейса (217, 30)
  оставлены: `verification/chain.toml` подставляет их по значению. История в этом файле и в
  `docs/superpowers/plans/` не переписывалась.

  **Проверено:** юнит-тесты — 304, OK; `claude plugin validate . --strict` — OK;
  eval-сьют `claude plugin eval . --ablation none` — все 36 прогонов (12 кейсов × 3) со
  счётом 1.00, в том числе `routing-catalog`, чьё описание менялось; живой прогон
  `scripts/denodo verify --env lab --with-marketplace --update-marks` на 9.5.1 — 19 шагов,
  0 падений, уборка прошла, 14 пометок переписаны генератором в новом формате
  `(live, 2026-09-17)`, то есть парсер и генератор пометок проверены сквозь живой сервер.

- **T19. Приёмка вехи B: от фразы до публикации в маркетплейсе. Веха B закрыта.** Два
  последовательных прогона субагентами по методу T13: папка со всеми семью навыками (копии в
  scratchpad, `scripts/` рядом, `docs/` и `spikes/` — нет, иначе сигнатуры маркетплейса
  списываются из отчёта T11), одна фраза, без указания, какой навык брать. Данные подобраны
  так, чтобы не повторять ни один шаблон и ни одну прошлую приёмку: `call_center` +
  `catalog_returns` — SCD-дименсия (6 суррогатных ключей на 3 центра) и 2 851 факт из
  144 067 без ключа.

  **Замер.** A (витрина возвратов по колл-центрам плюс разметка в маркетплейсе тегом и
  категорией) — 33 вызова, 0 неудач. B (внешний элемент Acme BI поверх витрины A) — 19
  вызовов, 0 неудач. Ни один VQL-оператор не потребовал второй попытки, ни один REST-вызов
  не вернул не-2xx.

  **Проверено мной, а не по отчётам.** Витрина A сходится с эталоном, посчитанным по CSV до
  прогона, до копейки: NY Metro 47 427 / 61 197 362.26, Mid Atlantic 46 987 / 60 729 129.73,
  North Midwest 46 802 / 60 046 929.09, «не указан» 2 851 / 1 828 573.43; сумма строк витрины
  ровно 144 067 — джойн не потерял и не удвоил. Дименсия схлопнута до трёх центров.
  `GET_VIEWS(… invalid only)` пусто в обеих базах. Тег и категория проверены с четырёх сторон,
  внешний элемент — карточкой (`openInInfo.openInStrategy.openInUri`) и, главное, графом со
  стороны витрины: ребро `OUT`/`consumes` к узлу `633`, узел витрины резолвился в
  `databaseName`/`viewName`/`viewSubtype`, а не остался строкой.

  **Главная находка — навык провоцировал ровно ту беду, от которой предостерегает.** Рецепт
  `SUM(CAST('long', x))` объясняет переполнение `int`, но императив был написан для «любой
  фактовой колонки». На денежной колонке тот же CAST усекает каждую строку до сложения:
  183 734 747 против верных 183 801 994.51, без ошибки и предупреждения (проверено на стенде
  в этой же задаче). Императив ограничен `int`-колонками, цена ошибки названа цифрой.

  **Второе — правило безопасности запрещало последний шаг штатной цепочки.** Импорт внешнего
  элемента — это `POST /external-tool-servers/synchronize`, а `synchronize` требует
  подтверждения человека, которого в сценарии нет. Агент B прошёл шаг, обосновав это тем,
  что сервер создан минуту назад и удалять ему нечего, и честно вынес нарушение буквы в
  отчёт. Правило разведено по факту: первый импорт на своём только что созданном сервере
  удалить не может ничего, со второго подтверждение возвращается. Заодно выяснилось, что
  `GET …/external-tool-servers/{id}/external-elements` не существует (`404`) — набор
  элементов сервера читается поиском с фильтром; вписанный по первому наитию путь пришлось
  проверить и заменить.

  **Третье — шаг «прочитай контракт и примени как VQL» вводил в заблуждение.**
  `vql-metadata` отдаёт интерфейсное представление **без** `SET IMPLEMENTATION` и `FOLDER`
  (проверено): применённое буквально, оно даёт `INTERFACE_NOT_IMPLEMENTED`, и импорту нечего
  читать. Дословно берутся только два `CREATE TYPE`.

  **Четвёртое — три ссылки вели на `/denodo:query`, которого в наборе нет.** Для пользователя
  плагина это тупики. Вместо них сказано прямо: `SELECT` — обычный SQL, а дельты диалекта
  лежат там, где кусаются.

  Остальные правки из ревью: признак SCD-дименсии (пара колонок валидности) вместо одного
  демо-примера; случай «проекта нет — файл всё равно пишется»; выбор родителя категории в
  чужой таксономии; два базовых пути тегов как свойство API; размер ответа `view-details`
  (16 289 байт против трёх нужных полей); имена объектов цепочки внешнего элемента — вне
  конвенции именования, и теперь сказано почему; разнобой `200`/`201` у двух соседних `POST`
  (проверен отдельным пробным сервером, убранным сразу); дата без времени и пустое описание
  в контракте внешнего элемента.

  **Оговорки, честные.** Ноль неудач в обоих прогонах — не мера сообразительности агентов, а
  следствие того, что порядок и синтаксис взяты из шаблонов почти дословно; агент B отметил
  это сам. Приёмка мерила смыкание цепочки, а не устойчивость к незнакомому. Прогон B стоял
  на витрине прогона A и получил её уже синхронизированной в каталог — ветка «представления
  ещё нет в маркетплейсе, сначала синхронизируй» этой приёмкой не проверена, хотя навык её
  описывает. Срабатывание по `description` здесь тоже не меряется — это eval-сьют T9.
  Заявки субагентов проверены в обе стороны: неверных не нашлось, одна (`SUM`) была
  заявлена мягче, чем есть.

  **Проверено (9.5.1, стенд `lab`, 2026-09-12).** `scripts/denodo verify --env lab
  --with-marketplace` до приёмки — 19 verified, 0 упавших, и он же после правок — снова 19
  verified, 0 упавших, уборка полная. Юнит-сьют — 304 теста, OK. Eval-сьют не гонялся: ни
  один `description` не менялся. Уборка приёмки полная: обе базы удалены, тег, категория,
  tool server (уносит элемент) и тип провайдера удалены, типов провайдеров снова 28; записи
  удалённой базы остались в каталоге маркетплейса как `localElements` (1 база + 4
  представления) и убраны синхронизацией — по обеим половинам `changes` пуст.

- **T14. Навык `procedures`: предопределённые, VQL и Java, разведённые по статусу.**
  Шестой доменный навык и первый вне объёма v1. Три шаблона вместо двух ожидавшихся:
  вызов предопределённой процедуры, `CREATE OR REPLACE VQL PROCEDURE` и Java-форма
  `CREATE PROCEDURE … CLASSNAME … JARS`. Развилка «`CREATE PROCEDURE` и
  `CREATE VQL PROCEDURE` — разные объекты» стоит первым абзацем: пропущенное слово `VQL`
  даёт `Syntax error near '('`, и без подсказки это выглядит как ошибка в теле.

  **Сплиттер пришлось учить телу процедуры.** Точка с запятой внутри `AS (…)` и между
  командами `BEGIN … END` — часть синтаксиса, а `split_statements` резал по ней: одна
  процедура уходила на сервер пятью обрубками. Теперь тело держится целым до `END`,
  который его закрывает, а `END IF`, `END LOOP` и `END CASE` закрывают вложенный блок.
  Один именованный частный случай, не парсер VQL. Заодно комментарии внутри тела
  перестали вырезаться — тело есть текст пользователя, слой исполнения его не правит;
  сервер их всё равно не хранит, и в reference это сказано прямо.

  **Что стенд рассказал против ожиданий.** `FOLDER =` у VQL-процедуры стоит **перед**
  списком параметров (так печатает сам сервер в `DESC VQL PROCEDURE`), у Java-формы — среди
  прочих клауз. Границы `FOR … IN a .. b` обязаны быть литералами, а счётчик цикла в теле
  не читается — считать приходится своей переменной через `LOOP`/`WHILE`. `EXIT WHEN`
  обязан стоять последним в теле `LOOP`. Тело связывается поздно: процедура со ссылкой на
  несуществующий вью создаётся молча и падает при вызове глухим `Error executing query`,
  тогда как `WHEN OTHERS (e)` внутри самой процедуры отдаёт настоящее сообщение — это
  теперь рецепт диагностики в reference. `USED_BY` процедуру не принимает вовсе, обратный
  вопрос задаётся через `VIEW_DEPENDENCIES`.

  **Цепочка verify выросла на два шага.** VQL-процедура пишется в тестовую базу, и её
  `check` — вызов, а не поиск в `GET_ELEMENTS`: из-за позднего связывания «объект есть» и
  «объект работает» здесь разные факты. Второй шаг исполняет шаблон вызова предопределённой
  процедуры. Java-шаблон в цепочку не взят сознательно: ему нужен импортированный в сервер
  JAR, которого прогон обеспечить не может, и его пометка остаётся `unverified`.

  **Названо то, что инструмент не ловит.** Вызов процедуры, меняющей состояние, выглядит
  как `SELECT`, и `safety.py` считает его безобидным. Вынесено в открытые вопросы.

  **Проверено (9.5.1, стенд `lab`, 2026-09-12).** Юнит-сьют — 304 теста, OK (было 293).
  Прогон цепочки — 13 verified, 0 упавших, 6 пропущено (маркетплейс без флага), уборка
  полная; `--update-marks` проставил дату двум новым шаблонам и не тронул чужие. Eval-сьют
  прогонялся дважды: обкатка `--runs 1` — 14 из 14, полный прогон по три захода — те же 14 из 14, каждый кейс 1.00 при 100 % pass.
  Прогон был обязателен: описания конкурируют между собой, и шестое описание — повод
  проверить, не увело ли оно чужие фразы.

- **T18. Цепочка `verify` расширена: источники JSON и JDBC, внешний элемент целиком.**
  Было десять шаблонов в прогоне, стало семнадцать шагов. Три из них — источники, чьи
  пометки до сих пор стояли по разовым прогонам T8b: JSON, JDBC и рукописный JDBC-wrapper
  с базовым представлением. Предмет у них тот же, что у CSV-шага: синтаксис без самого
  источника (раздел 11.1 спеки), поэтому `check` спрашивает `GET_ELEMENTS()`, а не
  `SELECT`. Блок интроспекции (`PING_DATA_SOURCE`, `GET_JDBC_DATASOURCE_TABLES`,
  `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW`) в цепочку сознательно не взят: ему нужна
  отвечающая база, то есть настоящий креденшел, которого у цепочки нет по построению.

  **Пароль решён маркером, а не литералом.** Шаблон JDBC несёт `USERPASSWORD … ENCRYPTED`,
  и сервер проверяет шифр при создании — `Invalid encrypted value` на любую строку, которую
  он не шифровал сам (проверено на стенде). Настоящий шифр — креденшел, привязанный к
  выдавшему серверу, в репозитории ему не место. Поэтому `[values]` объявляет намерение
  (`jdbc_password = "@encrypt-throwaway"`), а прогон шифрует случайную пустышку на том
  стенде, куда собирается писать. Дешёвая альтернатива — переписать шаблон на плейнтекст
  без `ENCRYPTED` — кода не требует и проверяет меньше, чем заявляет пометка блока.

  **Отказ T12 по внешнему элементу снят — он стоял на неверном прочтении.** Считалось, что
  шаблон применяет VQL, сгенерированный ответом `GET …/vql-metadata`, а исполнитель тело из
  чужого канала передать не умеет. На деле навык приводит VQL-половину **отдельным блоком**:
  шаг исполняет её verbatim, а `vql-metadata` — вызов, который надо совершить, а не тело,
  которое надо исполнить. Через каналы передаётся идентификатор, и это давно умеет
  `capture`. Итог — четыре шага: тип провайдера → tool server → VQL-половина → импорт, плюс
  два `DELETE` в уборке. VQL-половина исполняется и в базовом прогоне (она пишет только в
  свою базу) и стоит перед `nothing-invalid`, так что проверка «сломанных представлений нет»
  накрывает и её вью.

  **Что пришлось починить в исполнителе, чтобы он читал то, что написано в навыке.**
  Во-первых, `--part` он молча отбрасывал вместе со значением — единственный multipart-вызов
  маркетплейса уходил бы на сервер с пустым телом. Во-вторых, он читал строку за строкой и
  спотыкался о `--json`, тело которого в шаблоне занимает три строки внутри одних кавычек:
  это обычный bash (обратный слэш там попал бы **внутрь** JSON), то есть неполон был
  исполнитель, а не шаблон. Обе правки — в `parse_api_calls`, обе с тестами.

  **Цена, названная прямо.** Три http-шага делят один блок, потому что каждый идентификатор
  надо захватить до следующего вызова. Вместе они исполняют все четыре вызова блока, но
  `--update-marks` спрашивает «исполнил ли блок целиком» про шаг, а не про блок, — и пометку
  этого блока не обновляет ни один прогон. Вынесено в открытые вопросы.

  **Проверено на живом стенде (9.5.1, 2026-09-12).** Базовый прогон — 11 verified, 6
  пропущено; `--with-marketplace` — 17 verified, уборка полная; `--update-marks` обновил
  даты у одиннадцати блоков и отказался у пяти частичных, назвав причину. Отдельно проверен
  сам предмет, а не только статус ответа: прогон с `--keep` показал в каталоге импортированный
  элемент (`ACME-DASH-01`, `DASHBOARD`), а после уборки его нет — удаление tool server
  уносит элементы с собой; остатки `--keep`-прогона убраны руками, каталог `changes` чист по
  обеим половинам. Юнит-сьют — 293 теста, OK; интеграционный — 5 тестов против стенда, OK,
  включая новый, который ищет элемент поиском маркетплейса и сам за собой убирает.
  Eval-сьют не гонялся: ни один `description` не менялся.

- **T17. Хвост маркетплейса в `verify`: отказ оставлен, но объяснён.** Решение — шаг
  ветвящимся не делать. Идемпотентность стоила бы конструкции «прочитать, потом решить» в
  модели шага, то есть того самого интерпретатора поверх манифеста, которого избегает
  раздел 11.1 спеки. Второй рассмотренный путь — уникальные имена на каждый прогон —
  коллизии убирал, но взамен объекты каждого `--keep`-прогона тихо оседали бы в **общем**
  каталоге маркетплейса, а `409` — единственное, что сейчас заставляет их убрать. Громкий
  отказ выбран сознательно, и раздел 11.1 теперь называет это принятым свойством, а не
  пробелом.

  **Что изменилось в коде.** `409` приходит с пустым телом, поэтому отчёт показывал
  `status: 409, body: null` — правду, из которой оператору ничего не следовало. Ошибка
  http-шага теперь несёт `hint`: причина (имя занято) и два `DELETE`, которыми остаток
  убирается руками. Подсказка берётся из таблицы `HTTP_HINTS` по статусу; единственный
  статус в ней — `409`, у прочих ошибок поля `hint` нет, и на это есть отдельный тест.
  Подсказка на каждой ошибке рано или поздно объяснила бы `400` как остаток и отправила бы
  искать объект, которого никто не создавал.

  **Границы.** Конверт `denodo api` не менялся: там читатель — агент, и строка про `409` с
  пустым телом у него есть в `skills/execute/references/errors.md`. Хвост маркетплейса
  по-прежнему не проверяет ветку `PUT` шаблона тега — цена решения, вынесенная в открытые
  вопросы.

  **Проверено на живом стенде (9.5.1, 2026-09-12) четырьмя прогонами подряд, включая
  отрицательный контроль:** `--with-marketplace` зелёный (10 verified, уборка прошла) →
  тот же прогон с `--keep` (10 verified, остались тег 641 и категория 366) → третий прогон
  упал ровно на `marketplace-tag` с `409` и подсказкой в отчёте, а его уборка пропустила
  оба `DELETE` по неразрешённым `{tag_id}`/`{category_id}` и всё же вернула каталог в
  исходное состояние двумя `synchronize` → остатки убраны рецептом из самой подсказки
  (`DELETE /public/api/tags/641`, `DELETE …/categories/366`, оба `200`), после чего каталог
  не содержит ни объектов с префиксом `verify_`, ни тестовой базы, а четвёртый прогон снова
  зелёный. Юнит-сьют — 279 тестов, OK. Eval-сьют не гонялся: ни один `description` не
  менялся.

- **T10. README и CONTRIBUTING.** Публичных файлов два, а не один: `README.md` — вход для
  того, кто ставит плагин (что это, требования, установка, профиль среды, быстрый старт,
  таблица шести навыков, границы v1, безопасность), `CONTRIBUTING.md` — для того, кто
  делает навыки здесь же. Разнесено потому, что GitHub сам показывает `CONTRIBUTING.md`
  при создании PR и issue, то есть ровно тому человеку, которому он адресован, а README
  при этом остаётся читаемым за две минуты.

  **Контрибьюторский файл закрывает языковую дыру, а не пересказывает спеку.** Проектная
  документация русская, и англоязычный человек до сих пор не мог узнать из репозитория ни
  скелета `SKILL.md` из пяти блоков, ни правила пометок `verified:`, ни того, что на общем
  стенде пишут только в свою базу. Всё это изложено по-английски со ссылкой на то, что
  `docs/` читать не обязательно. Примеры пометок взяты из живых шаблонов
  (`-- verified: 9.5.1 (стенд, 2026-09-09)`), а не из спеки, и про русскую формулировку
  самой пометки сказано прямо — иначе контрибьютор решит, что это опечатка, и начнёт
  переводить.

  **Проверено:** `claude plugin validate . --strict` проходит; юнит-тесты — 277, OK;
  команда интеграционных тестов из CONTRIBUTING отрабатывает (без `DENODO_TEST_ENV` даёт
  корректный skip десяти тестов); глоб пути к launcher'у из установленного плагина
  (`~/.claude/plugins/cache/denodo-skills/denodo/*/scripts/denodo`) резолвится; поля
  профиля, конвенции именования и все команды CLI сверены с кодом и справкой, а не
  написаны по памяти. **Не проверено и в тексте как проверенное не заявлено:** установка
  с GitHub — она заработает только после мерджа в `main`.

- **T3. Лицензия MIT.** Решение владельца репозитория. `LICENSE` в корне, `"license":
  "MIT"` в `.claude-plugin/plugin.json` (поле до сих пор намеренно пустовало), раздел в
  README. Правообладателем указан ник `kirivandubai` — тот же, что в `author.name`
  манифеста; настоящее имя в публичный репозиторий не выносилось.

- **T16. `serverId` маркетплейса приходит из профиля.** Транспорт был прав с самого начала
  (`api_rest.py:52` подставляет `marketplace_server_id`, только если вызов сервер не назвал);
  чинить надо было источник значения. Литеральный `serverId=306` убран из всех пятнадцати
  примеров `skills/marketplace/SKILL.md`, а вместе с ним — `server_id` из `[values]`
  манифеста, три подстановки шагов и параметр у четырёх записей `[cleanup].http`. Теперь
  форк, проверяющийся на своём маркетплейсе, указывает сервер одним полем профиля и репозиторий
  не трогает.

  **Раздел «Name the server» переписан под одно правило:** id живёт в профиле, транспорт
  вешает его сам, а `--param serverId=…` остаётся перекрытием на один вызов — ровно для
  диагностики «спроси каждый сервер, чей `inLocal: true`», которой навык же и учит. Строки
  таблиц в самом навыке и в `skills/execute/references/errors.md` выровнены под тот же
  порядок: профиль первым, `--param` — как временная мера.

  **Механизм проверен отрицательным контролем, а не зелёным прогоном.** На стенде
  зарегистрированы два VDP-сервера (306 «Demo Standard Default» и 206 «Verticals»), и один
  и тот же read-only `GET /public/api/tag-management/tags` отвечает `200` с
  `marketplace_server_id` в профиле и `500 GENERIC "Session Expired."` без него — то есть
  подстановка из профиля действительно несущая, а не совпадение.
  *verified: 9.5.1 (стенд, 2026-09-12)*

  **Страховка от возврата — офлайн-тест** в `tests/test_chain_manifest.py`: ни одно
  отрендеренное тело http-шага и ни одна запись `[cleanup].http` не должны нести `serverId`.
  Написан до правки и на прежнем манифесте падал семь раз. `tests/integration/
  test_verify_chain.py` перестал читать `chain.values["server_id"]` и зовёт `/changes` без
  параметров, так что его прямая проверка каталога сама стала доказательством профильного пути.

  **Прогоны:** юнит-сьют 277 тестов, `verify --env lab --with-marketplace` дважды подряд
  (10 verified, 0 failed, 0 skipped), интеграционный `test_verify_chain` — четыре теста,
  включая хвост маркетплейса. Eval-сьют не гонялся: ни один `description` не менялся.
  Пометки `verified:` у блоков вне цепочки (внешний элемент) оставлены — запрос на проводе
  тот же, изменилось лишь то, кто ставит параметр.

  **Профиль `lab` теперь несёт `marketplace_server_id = 306`** — вне репозитория,
  в `~/.denodo/profiles.toml`; без этого поля цепочка на стенде с двумя серверами не пройдёт.

- **T15. Секреты источников в слое исполнения.** `scripts/denodo secret encrypt --env <env>`
  заменяет трёхшаговый рецепт T8b одной командой. Пароль читается со stdin: в терминале —
  скрытым промптом `getpass`, иначе как есть (пайп из парольного менеджера или CI). Срезается
  ровно один перевод строки — пробелы могут быть частью пароля, перевод строки не может;
  пустой и многострочный ввод — usage-ошибка, до сервера дело не доходит.

  **Команда сознательно не идёт через `run_statements`.** Тот кладёт текст выражения и в
  успешный результат, и в ошибку, а выражение здесь целиком состоит из пароля. Сверх этого
  сообщение сервера перед печатью чистится от пароля: ошибка вида «syntax error near
  ENCRYPT_PASSWORD '…'» иначе вернула бы плейнтекст в транскрипт — ровно то, ради чего
  команда и заводилась. На это есть тест с фейковым транспортом, который такую ошибку
  имитирует.

  **Экранирование проверено на живом парсере, а не рассуждением.** Восемь строк (`'`, `\`,
  `%`, `"`, таб, юникод, краевые пробелы) отправлены через тот же `quote_literal` в
  `SELECT <литерал> FROM DUAL()` и вернулись байт в байт: удвоение одинарной кавычки —
  единственное, что нужно, обратный слэш в литерале VQL буквальный.
  *verified: 9.5.1 (стенд, 2026-09-12)*

  **`ENCRYPT_PASSWORD` солёный.** Два вызова на одном пароле дают разные строки — поэтому
  доказать корректность сверкой шифров нельзя, и проверка построена иначе: шифр пароля
  `admin` лёг в JDBC-источник на сам VDP (`jdbc:denodo://…:9999/admin`, эталон синтаксиса —
  источник `Denodo Metadata Dashboards`), `PING_DATA_SOURCE()` отвечает `UP`. Отрицательный
  контроль тем же вызовом: шифр заведомо неверного пароля даёт `DOWN` и
  `The username or password is incorrect` — значит сервер шифр расшифровал и действительно
  им аутентифицировался. Всё DDL — в своей базе `denodo_skills_t15`.

  **Побочно: `CREATE DATABASE IF NOT EXISTS` в 9.5.1 — синтаксическая ошибка** (`Exception
  parsing query near 'IF'`). В первом прогоне из-за этого не сработал следующий за ним
  `CONNECT DATABASE`, и два тестовых источника создались в `admin`; убраны сразу же,
  `GET_ELEMENTS()` по `admin` чист. Урок для шаблонов: `CONNECT DATABASE` после `CREATE
  DATABASE` в одном файле молча продолжает работать в прежней базе, если создание упало, —
  надёжнее `--database`.

  **Вне объёма осталось намеренно:** подстановка `@{secret:<имя>}` при применении файла и
  `FROM_VAULT`. T15 помечал их «по потребности», потребности пока нет — запись в открытых
  вопросах.

- **T9. Eval-сьют навыков.** `evals/` — двенадцать кейсов, фразы английские. Шесть в группе
  `routing` (по одной однозначной фразе на навык) ловят полный отказ описания; шесть в группе
  `discrimination` бьют по границам, где описания конкурируют, и несут заодно отрицательный
  грейдер. Первые две пары закрывают риск, ради которого сьют и заводился: «тег» в VDP и
  «тег» в маркетплейсе — разные объекты на разных серверах, и перепутанный навык уходит
  корректным вызовом не туда.

  **Грейдеры детерминированные.** Все — `tool_used` с `tool: Skill` и `input_match` по имени
  навыка: читают трассу прогона и считают вызовы. Ни LLM-судьи, ни обращений к стенду, ни
  креденшелов — сьют гоняется где угодно и ничего не стоит сверх самих прогонов агента.
  Отрицательная форма требует явного `min: 0`: без него `min` остаётся единицей и условие
  вырождается в невыполнимое «от 1 до 0».

  **Что `input_match` действительно различает навыки — проверено фальсификацией, а не на
  слово.** В тот же прогон добавлялся грейдер, обязанный упасть, и он упал: `denodo:catalog`
  → один вызов, `denodo:marketplace` → ноль. Без этой проверки положительные грейдеры
  проходили бы на любом вызове `Skill`, и вся группа `discrimination` была бы фикцией.

  **Обкатка нашла дефект теста, а не описаний.** При одном заходе два кейса упали с нулём
  вызовов предметного навыка. По трассам видно, что произошло: агент вызывал `/denodo:vql`
  (штатно — это точка входа), а дальше сжигал лимит ходов на `Glob` по пустой песочнице и до
  предметного навыка не доходил. Прогон мерил разведку файловой системы, а не маршрутизацию.
  Лечится `append_system_prompt` с фактами об окружении: файлов нет, профилей нет, сервера
  нет, отвечать прозой. После этого ни один прогон в лимит ходов не упирается.

  **Замер.** Из репозитория: 12 кейсов × 3 захода = 36 прогонов, все 1.00, 100 % — 402 с,
  $9.58. Контрольный прогон на **установленном** плагине (`claude plugin marketplace add ./`
  + `claude plugin install denodo@denodo-skills`, запуск из `/tmp`, один заход на кейс):
  12 из 12, 1.00 — 127 с, $2.90; в шапке прогона видно, что плагин резолвился из
  `~/.claude/plugins/cache/denodo-skills/denodo/0.1.0`, а не из текущей директории. Это и
  есть разница между «навык применён» и «навык выбран сам», которую T13 не закрывал: там
  навыки подсовывались копиями в scratchpad.

  Команда прогона записана в `CLAUDE.md`, устройство кейсов, рецепт контрольного прогона и
  разбор падений — в `evals/README.md`; `evals/results/` в `.gitignore`.

  **Побочно.** Установка копирует в кэш плагина и `evals/results/` — `.gitignore` на
  копирование не влияет, так что каталог результатов стоит подчищать перед установкой.
  Среда после проверки возвращена в исходное: плагин удалён, локальный маркетплейс снят.

- **T13. Приёмка: сквозной сценарий. Веха A закрыта.** Три субагента, каждый — одна фраза на
  естественном языке и папка из шести навыков (копии в scratchpad с подставленным
  `${CLAUDE_PLUGIN_ROOT}`, метод T8a), своя база `denodo_skills_t13_a|b|c`, прогоны
  последовательные. Какой навык брать и в каком порядке, не подсказывалось.

  **Проверено мной, а не по отчётам.** `SELECT` из витрин отдаёт 7200 / 36 / 6 строк;
  `GET_ELEMENTS()` показывает в каждой базе два DF-источника, два wrapper'а, два базовых и
  одно-два производных представления плюс папки; `GET_VIEWS(… invalid only)` пусто во всех
  трёх. Перед приёмкой `scripts/denodo verify --env lab` прошёл целиком — иначе провал
  прогона можно было бы списать на сломанный шаблон, а не на текст навыка.

  **Замер.** A (домохозяйства и доходные группы, фраза бизнесовая, схема не дана) — 16
  вызовов, 0 неудач. B (веб-возвраты и причины, схема не подсказана вовсе, NULL'ы в ключе и
  в мере) — 12 вызовов, 0 неудач. C (магазины и возвраты; не сказано, где файлы, и запрошен
  разрез, которого в данных нет) — 30 вызовов, 0 ошибок сервера. Ни один `.vql` не
  потребовал второй попытки ни в одном прогоне.

  **Содержательно главный — C.** Канала продаж в данных нет: агент прочитал заголовки всех
  трёх файлов возвратов, установил, что к магазину привязан ровно один канал (у
  `catalog_returns` и `web_returns` ссылки на магазин нет — проверено мной отдельно), оставил
  колонку литералом `'store'` с путём расширения через `UNION ALL` и назвал дыру в отчёте.
  Требуемое поведение пришло из общего правила ядра «не выдумывать», в текстах доменных
  навыков его не было — теперь есть.

  **Что приёмка нашла в навыках** (всё проверено на стенде 9.5.1 2026-09-12 и правится в этой
  же ветке). Главное: **`SUM` над `int` остаётся 32-битным и молча отдаёт неверное число** —
  на фактовой колонке из 68 636 значений `SUM(x)` вернул `1140298269` там, где верная сумма
  `168668968269` (сверено `AVG × COUNT`), и **повторяется стабильно**, то есть читается как
  настоящая цифра; на минимальном случае с переполнением возвращается `NULL`. Ни ошибки, ни
  предупреждения. Рецепт `SUM(CAST('long', x))` ушёл в таблицу типов агрегатов.
  Дальше по файлам:

  - `execute` — строка про `--vql` читалась наоборот: команда собирает то, **от чего** объект
    зависит, а не то, что зависит от него, поэтому спрашивать надо базовое представление
    (вся цепочка с типами), а не источник (только он сам, без колонок). Плюс квалифицированное
    имя (`"other_db.bv_x"`) читает чужую базу, не переключая свою, и `vql desc` кладёт
    `columns`/`rows` на верхний уровень конверта, а не в `statements[]` — на этом C потерял вызов.
  - `datasources` — способ «прочитать существующий объект над тем же файлом» вёл к источнику
    и стоил трёх шагов; теперь это один вызов к базовому представлению и он идёт первым, раньше
    «спросить человека», когда донор на сервере есть. К нему две оговорки, которых не было:
    донор даёт грамматику, но не дефолты (`IGNOREMATCHINGERRORS = FALSE` добавляем сами,
    у серверных источников его нет) и пишет метки заголовка в кавычках и капсом — это не
    признак устаревшего шаблона, отображение всё равно позиционное. И предупреждение про
    усечение: `GET_ELEMENTS()` на стенде отдаёт 125 источников при дефолтных 100, а усечённый
    ответ выглядит ровно как «объекта нет». В таблицу Verify добавлена набивка пробелами
    (`"0-500          "`) — ломает любое сравнение у потребителя, не ломая ничего при создании.
  - `views` — `COUNT(DISTINCT x)` и выражения над сгруппированными колонками под `GROUP BY`
    работают (агент B обошёл их, решив по единственному примеру, что рискованно); `INNER`
    молча теряет факты (10 062 из 287 514 демо-возвратов магазинов без ключа магазина) —
    описан выбор между `LEFT OUTER JOIN` с меткой группы и честной цифрой в `DESCRIPTION`;
    дименсию надо считать до джойна (`store` — 12 строк на 6 магазинов, джойн по бизнес-ключу
    удвоил бы витрину); в Verify добавлена проверка «джойн не потерял факты»; развилка `/02`
    против `/03` разрешена для случая «потребитель читает сам джойн». Новый раздел — **что
    делать, когда запрошенного разреза в данных нет**: установить чтением, выбрать одно из
    трёх и сказать человеку.
  - `vql` — папки-слои создаются только те, что заполняются; конвенция `ds_<source system>`
    уточнена для файловых источников, где одна система даёт несколько файлов.

  **Что не подтвердилось.** Заявка A, будто `ENDOFLINEDELIMITER` не описан нигде, неверна —
  он есть в `references/df.md` и в грамматике, и в таблице клауз; агент просто не дошёл до
  справочника. Претензия к «`.denodo/conventions.md` в project root» тоже снята: текст
  говорит «если у проекта он есть», агент проверил и пошёл дальше.

  **Оговорки к замеру, честные.** Сценарий A почти copy-paste: шаблон derived view в `views`
  построен буквально на той же паре демо-файлов, и субагент это сам отметил — обобщение мерят
  B и C. Прогоны шли последовательно, но объекты предыдущего прогона остаются видны на стенде;
  донором C по своему отчёту была база `sources`, так что измеренного загрязнения нет.

  **Осталось.** Контрольный прогон на **установленном** плагине: приёмка мерила исполнение
  навыков, а не срабатывание по `description`, — это ушло в T9, которому установленный плагин
  нужен и так.

  Тесты: юнит-сьют 261 пройден, 12 пропущено без стенда; `scripts/denodo verify --env lab`
  зелёный после правок. Один тест поправлен осознанно: `tests/test_templates.py` адресовал
  блок «When you cannot see the file[1]», а вставка нового блока сдвинула нумерацию — тест
  ровно для этого и написан, теперь сверяет все три блока секции.

- **T12. `scripts/denodo verify`.** Подкоманда гоняет план из `verification/chain.toml`
  (механика в `denodo_cli/commands/verify.py`, `templates.py`): семь шаблонов цепочки из
  T1 на VQL-канале — база каталога, папки, DF/CSV-источник, производные представления,
  интерфейсное представление, ассоциация, теги, — с уборкой в `try/finally` и
  простановкой пометок по `--update-marks`. HTTP-канал — только marketplace-хвост
  (синхронизация каталога, тег, категория), по флагу `--with-marketplace`, по умолчанию
  выключен. Флаги: `--env`, `--chain`, `--database`, `--with-marketplace`, `--keep`,
  `--update-marks`, `--allow-destructive`.

  **Стенд поправил раздел 11.1 спеки.** `GET_SERVER_INFO()` на 9.5.1 не существует
  (`View 'get_server_info' not found`); версию для `--update-marks` берёт `SELECT
  version()`, отвечающий строкой `Denodo Virtual DataPort 9.5.1` — номер версии в её
  хвосте, вытащен регулярным выражением, а не позицией токена. `DROP TAG` отказывает,
  пока тег назначен хотя бы одному представлению, поэтому порядок уборки жёсткий: сперва
  `DROP DATABASE … CASCADE` снимает представления вместе с назначениями, только потом
  уходят оба `verify_`-тега. DF-источник над несуществующим путём создаётся без единой
  ошибки — падает только `SELECT`, что раздел 11.1 уже утверждал прозой, а T12 подтвердил
  кодом. Два шаблона `views` (интерфейсное представление и ассоциация) не несут своего
  `CONNECT DATABASE` — навык полагается на то, что сессия уже подключена командой,
  поэтому шаг манифеста сам называет базу, в которой выполняется, вместо того чтобы
  полагаться на сессию, оставленную предыдущим шагом.

  **Ревью ветки нашло и закрыло шесть дефектов.** Главный: marketplace-хвост
  синхронизировал общий каталог *после* того, как цепочка создала свою базу и шесть
  представлений, то есть импортировал их в каталог, который делят все, а уборка удаляла
  только тег и категорию. Прогон рапортовал зелёным и оставлял сирот (`localElements` в
  `.../changes`); на стенде они и лежали. Починка — в манифесте: те же два вызова
  `synchronize` повторяются в конце `[cleanup] http`, после `DROP DATABASE … CASCADE`, и
  тогда они означают обратное — убирают из каталога то, чего больше нет в VDP; ради этого
  запись `[cleanup] http` научилась нести тело запроса. Остальные пять: отказ на
  production-профиле переехал с уборки на весь прогон (`CREATE OR REPLACE` не
  разрушительный, поэтому старая проверка пропускала создание всего и отклоняла только
  удаление — гарантированный мусор); `--update-marks` больше не датирует блок, из которого
  шаг исполнил лишь часть вызовов; разбор `api`-строк и индексов `calls` отвечает
  `ChainError`, а не трейсбеком (офлайновый тест дрейфа теперь сверяет каждый индекс с
  реальным блоком); `ChainError` из тела `run_chain` ловится в `cli.py` наравне с тем, что
  из `load_chain`; интеграционный marketplace-кейс проверяет не факт запуска уборки, а её
  результат — включая оба `changes`-эндпоинта.

  Тесты: юнит-сьют `PYTHONPATH=scripts python3 -m unittest discover -s tests -t . -q` —
  260 пройдено, 12 пропущено без стенда; интеграционный
  `tests/integration/test_verify_chain.py` под `DENODO_TEST_ENV`, его marketplace-кейс —
  под `DENODO_TEST_MARKETPLACE`.

  Не покрыто цепочкой и вынесено отдельными задачами: источники JSON и JDBC, чьи пометки
  стоят по разовым прогонам T8b, и внешний элемент маркетплейса — T18; манифест и шаблоны
  навыка `marketplace` несут `serverId` литералом вместо того, чтобы полагаться на
  `profile.marketplace_server_id`, который транспорт умеет подставлять сам, — T16;
  создание вместо сверки в marketplace-хвосте, из-за чего второй прогон над оставленными
  `--keep` объектами падает на `409`, — T17, сознательно не исправлено в рамках T12. T13
  (сквозной сценарий) может опереться на `verify` как на готовый прогон.

- **T8d. Навык `/denodo:marketplace`.** `skills/marketplace/SKILL.md` по разделу 8 спеки и
  три справочника — `references/tags.md`, `categories.md`, `external-elements.md`. Тот же
  порядок, что в T8c, но RED шёл **до** любых моих проб на стенде: объекты маркетплейса
  серверные, а не пообъектные по базам, и мои пробы утекли бы в базовый прогон целиком.

  **Замер.** Без навыка: 45 вызовов и 8 неудач на разметке (все восемь — `serverId`),
  73 вызова на повторяемости (15 из них — слепой перебор путей, пока не нашёлся
  `/v3/api-docs`), 60 вызовов и 15 неудач на внешнем элементе. С навыком: 25 вызовов и
  1 неудача, 44 и 1, 25 и 2, плюс четвёртый сценарий на незнакомых данных — 38 вызовов,
  3 неудачи, и все три на разведке справочных эндпоинтов, ни одной при записи. Оба
  VQL-файла четвёртого сценария применились с первого прогона.

  **Оба базовых прогона остановились сами перед разрушительным вызовом** — синхронизацией
  общего каталога и импортом тегов VDP, — и остановились по правилу из ядра, померив радиус
  чтением. Это ядро, а не новый навык; замер тут в другом: без навыка агенты дошли до этой
  точки за 45 и 73 вызова, с навыком — за 25 и 44.

  **Расхождения с отчётом T11, снятые на живом стенде** (demo-образ 9.5.1, база
  `denodo_skills_t8d`). `serverId` обязателен, как только зарегистрировано больше одного
  VDP-сервера, и наборы тегов и external tool server'ов у серверов **разные**; без него теги
  отвечают `500 "Session Expired"`, а external tool servers — `403`. `proceedWithConflicts`
  принимает три значения, безопасное по умолчанию — `SERVER_WITH_LOCAL_CHANGES`, а не
  `SERVER`, который единственный знал T11. Есть предпросмотр `GET …/{тип}/changes`. Цепочка
  внешнего элемента короче обещанных пяти шагов: 24 встроенных типа элементов и 28 типов
  провайдеров делают оба «создай тип» необязательными, а иконка провайдера не обязательна
  вопреки документации. Но цепочке предшествует синхронизация каталога — обе её половины,
  `DATABASES` и `VIEWS`: без них импорт отказывает целиком с `"The view … does not exist"`,
  хотя представление в VDP есть.

  **Три ловушки, которых нет ни в спайке, ни в документации.** Имя типа
  `external_element_association_array_type` сверяется буквально. `LEFT OUTER JOIN` в
  реализации ломает импорт элемента без связей (`NEST` рождает запись из одних `NULL`);
  рабочая форма — `INNER JOIN` плюс ветка `UNION ALL` с `NULL`-массивом. И асимметрия
  удаления: элемент, исчезнувший из **непустого** снимка, удаляется вместе с разметкой, а
  пустой снимок не удаляет ничего.

  **Что GREEN нашёл в самом тексте навыка** и что исправлено: ответ `view-details`
  `{"id":null,"inLocal":false,"inVDP":true}` означает не только «нужна синхронизация», но и
  «неверный `serverId`» — по букве первой редакции агент чинил бы параметр изменением общего
  каталога; рецепт идемпотентности обрывался на шаг раньше нужного (для CI читать надо
  **до** записи, иначе второй прогон получает `[viewId]`, который не читается ни как успех,
  ни как отказ); абзац про необязательный шаг путал тип элемента с типом провайдера;
  связь элемент↔элемент стояла непроверенной — четвёртый сценарий её проверил.

  **Заодно две дырки в ядре исполнения.** Точечный `element-management/{тип}/synchronize` и
  вся семья `external-tool-servers/synchronize` не помечались разрушительными вовсе, а путь
  `views/{id}/categories`, который классификатор стерёг, в API отсутствует — «сет»-вызов для
  категорий живёт под `category-management/`. И `env.database` в конверте всегда показывал
  базу профиля, игнорируя `--database`, то есть называл базу, в которой сессия не находится.

- **T8c. Навык `/denodo:views`.** `skills/views/SKILL.md` по разделу 8 спеки и три
  справочника — `references/derived.md`, `interface.md`, `associations.md`. Тот же TDD:
  три базовых сценария субагентами без навыка (витрина со связью, контракт с подменой
  реализации, правка представления с зависимыми), затем навык, затем четыре сценария с
  навыком — те же три плюс один на других данных (веб-возвраты и причины), чтобы отделить
  «шаблон применяется» от «навык обобщается».

  **Базовый прогон снова не провалился, а стоил попыток.** Как и в T8b, синтаксис все трое
  списали с чужих объектов сервера через `DESC VQL`. Цена: две попытки на порядок клауз
  `CREATE INTERFACE VIEW` и на имена типов в `CAST` (на последнее независимо наступили два
  агента из трёх), плюс восстановление синтаксиса `CREATE ASSOCIATION` со стенда у всех
  троих. С навыком все четыре сценария — по одной попытке на объект и **ноль ошибок
  сервера**, включая сценарий на незнакомых данных; каждый агент отдельно отметил, что
  таблица инверсии типов и порядок клауз интерфейса сэкономили ему попытку. Честная
  оговорка: базовый замер сценария C загрязнён — агент нашёл на стенде мои собственные
  пробные объекты и снял ловушку с них.

  Снято со стенда 9.5.1 (2026-09-10) и вошло в навык. **Порядок клауз** `CREATE VIEW`:
  `FOLDER → DESCRIPTION → PRIMARY KEY → TAGS → ( field properties ) → AS SELECT`, причём
  `TAGS` после свойств полей — синтаксическая ошибка. У `CREATE INTERFACE VIEW`
  `SET IMPLEMENTATION` стоит строго между списком полей и `FOLDER`. **Имена типов
  инвертированы**: в объявлении колонки `int`/`long`/`text`/`double`, в `CAST` —
  `integer`/`bigint`/`varchar`/`double precision`; двухаргументный `CAST('int', x)` берёт
  VQL-имена. `AVG` над int уже даёт double, `COUNT` — `long`, а `AVG(TO_DECIMAL(x))` под
  `GROUP BY` отвергается.

  **Два тихих отказа, ради которых навык и написан.** `CREATE OR REPLACE VIEW` с
  переименованной или удалённой колонкой принимается без ошибки, а всё, что стоит выше,
  уходит в `view_status = 'INVALID'`, и ассоциации, мапившие эту колонку, — в
  `valid = false`; само представление при этом продолжает отдавать строки. `SET
  IMPLEMENTATION` вообще не сверяет схему: несовпадающие имена, недостающее поле, три
  колонки под контрактом из семи — всё принимается, `DESC` показывает объявленную схему, и
  падает только `SELECT` сообщением `… <NAME> [INTERFACE] [ERROR]`, которое не называет ни
  поля, ни причины. Отсюда обязательные read-back'и: `GET_VIEWS(…
  input_retrieve_invalid_views_only = true)`, `GET_ASSOCIATIONS().valid`, `USED_BY()` до
  изменения и `SELECT` через контракт после.

  **Ассоциации документированы только в UI-разделах.** Страницы `CREATE ASSOCIATION` в
  публичном VQL Guide 9.5 нет вообще — шаблон снят с сервера. Разобрано и проверено:
  первый идентификатор после `ENDPOINT` — role name противоположного конца, а не алиас
  своей вьюхи; кратность означает «сколько строк ЭТОГО представления на одну строку
  другого» и пишется `(0,*)`, а не `0..1`; role name уникален в пределах представления;
  `PRINCIPAL` без `REFERENTIAL CONSTRAINT` принимается и молча игнорируется, то есть FK не
  появляется; принципал обязан быть `(1)` или `(0,1)`. Синтаксис role precondition —
  `PRECONDITION ( условие )` после кратности, условие в скобках, а не литералом — подобран
  перебором и проверен; в документации его нет ни в каком виде.

  Попутно поправлен `execute`: в таблицу типов `DESC` добавлены `association` и
  `interface view`, раздел про тихие отказы в `references/errors.md` развёрнут из одной
  строки в таблицу на пять случаев, добавлены предупреждения про `desc --vql` (это готовый
  скрипт с `DROP … CASCADE`, читать можно, применять нельзя) и про повторный `-e`.


- **T8b. Навык `/denodo:datasources`.** `skills/datasources/SKILL.md` по разделу 8 спеки и
  четыре справочника — `references/df.md`, `json.md`, `jdbc.md`, `base-view.md`. Писался по
  TDD для документации: три базовых сценария субагентами без навыка (CSV, JSON, JDBC),
  затем навык, затем четыре сценария с навыком. **Главный вывод базовых прогонов:** агент
  без навыка не проваливается, а выкручивается — все три списали синтаксис у чужих объектов
  сервера через `DESC VQL`. Это работает только там, где донор есть: JDBC-агент донора не
  нашёл, потратил три итерации на порядок клауз `CREATE DATASOURCE JDBC`, решил, что
  VQL Guide вообще не документирует JDBC-источники, и сдал файл, помеченный `unverified` по
  существу. Разведка стоила 5–8 read-only запросов, из них 4 падали на несуществующих
  командах (`LIST DATASOURCES` без типа, `LIST FOLDERS`, `LIST TABLES`).
  С навыком все четыре сценария прошли без единой неудачной инструкции: CSV с ловушкой
  «нужны только три поля», JSON с вложенным массивом, Oracle **без пароля вообще** (агент
  сам взял `USERPASSWORD … ENCRYPTED` из чужого источника в другой базе) и CSV с
  неизвестным заголовком (агент прочитал файл сервером через `TUPLEPATTERN = '(.*)'`).
  Приём «спроси сервер вместо памяти» (`DESC VQL` существующего объекта) вошёл в навык как
  штатный, а не как выход из положения.

  Снято со стенда 9.5.1 (2026-09-09) и вошло в навык. **DF:** маппинг `OUTPUTSCHEMA`
  **позиционный** — имена не сверяются с заголовком, поэтому неверный порядок молча кладёт
  значения под чужие имена, а неверное количество колонок даёт ноль строк, потому что
  `IGNOREMATCHINGERRORS` по умолчанию `TRUE`; `= FALSE` превращает это в
  `[DF ROUTE] [PARSE_ERROR] Invalid line found at data file` — теперь стоит в шаблоне.
  Типов в DF-wrapper нет ни в одном написании; типы задаёт `CREATE TABLE`, неверный тип
  возвращает колонку `NULL` без ошибки; `NULLVALUE ''` нужен только текстовым колонкам;
  кавычки в CSV снимаются сами; директория + `FILENAMEPATTERN` читается как одна таблица;
  `TUPLEPATTERN = '(.*)'` отдаёт файл построчно — единственный способ увидеть серверный
  файл из VQL. **JSON:** обёртка `jsonfile = 'JSONFile' : REGISTER OF (…)` обязательна —
  плоский `OUTPUTSCHEMA` создаётся и молча размножает строки по вложенным массивам;
  `TUPLEROOT '/JSONFile/JSONArray'`, абсолютные пути наверху и относительные внутри, имя
  элемента в `ARRAY OF` произвольно; compound-колонки требуют `CREATE TYPE`; `FLATTEN`
  разворачивает подполя без префикса. **JDBC:** `CLASSPATH` — имя каталога драйвера, а не
  путь к jar, и без него `DATABASENAME`/`DATABASEVERSION` падают с
  `Cannot invoke "java.util.List.size()"`; версия адаптера не валидируется; интроспекция
  делается сервером (`GET_JDBC_DATASOURCE_TABLES` — с фильтрами на входе, надёжна везде;
  `LIST_JDBC_DATASOURCE_TABLES` падает на SQL Server), а `GENERATE_VQL_TO_CREATE_JDBC_BASE_VIEW`
  возвращает **две строки** — wrapper и `CREATE TABLE`; `PING_DATA_SOURCE` различает сеть,
  драйвер и учётку; wrapper с подмножеством колонок работает (в отличие от DF); пул-клаузы
  сервер подставляет сам. **Пароли:** `ENCRYPT_PASSWORD` даёт шифр, который сервер
  принимает как настоящий пароль, шифр переносится между источниками одного сервера, а
  `CREATE OR REPLACE DATASOURCE` без клаузы пароля его **стирает**. Плюс общее:
  `FOLDER =` папку не создаёт, `LIST VIEWS` не показывает базовые представления
  (нужен `GET_ELEMENTS()`), `decimal` приходит из инструмента строкой в JSON — уточнение
  ушло в `execute`.

  Проверено на живых источниках: Oracle (20 000 строк), SQL Server (1 000 000),
  PostgreSQL (500 000). Не проверено и помечено `unverified`: Credentials Vault,
  Kerberos, OAuth, AWS IAM, GCP, pass-through session credentials, OpenAPI 3, NDJSON,
  HTTP/FTP/HDFS/S3-маршруты, интерполяционные переменные, `SQLSENTENCE`-генератор,
  процедурные wrapper'ы. Базовые прогоны шли на ontology-стенде (профиль `dev`, 9996),
  прогоны с навыком — на demo-стенде (профиль `lab`, 29996), где рядом подняты Oracle,
  SQL Server и PostgreSQL; обе машины 9.5.1.

- **T8a. Навык `/denodo:catalog`.** `skills/catalog/SKILL.md` по разделу 8 спеки (развилка,
  шаблоны базы, папок и тегов, что выяснить, ссылки, проверка, таблица ошибок) и три
  справочника `references/database.md`, `folders.md`, `tags.md` — полный синтаксис из VQL
  Guide 9.5 с пометками `verified:`/`unverified:` по каждой клаузе. Писался по TDD для
  документации: три сценария субагентами (теги на колонку и представление; новая база с
  `CHARSET` и деревом папок; уборка папок с `DROP` и переносом представления). Базовые
  провалы — справочные, не дисциплинарные: `CHARSET` перед описанием базы (ошибка
  `near '''`), `DESCRIPTION` без `=` у тега, пробный `LIST FOLDERS` (не существует),
  четыре разведочных вызова в поисках `GET_DATABASES()`, удаление папок без знания о
  `CASCADE`. С навыком все три сценария проходят с первой попытки; первый базовый прогон
  S1 пришлось переделать — субагент нашёл отчёт спайка T2 в репозитории через путь
  инструмента, для честной базы `scripts/` копируется в scratchpad. Снято со стенда 9.5.1
  (2026-09-09) и вошло в навык: теги **серверные, а не по базам** (`LIST TAGS` показывает
  все); `ADD_TO` на несуществующее представление или колонку **проходит молча** и не
  записывается — `GET_VIEW_TAGS()` после назначения обязателен; `CREATE OR REPLACE TAG` с
  новым `ADD_TO` добавляет назначения к существующим, а не заменяет; `DROP TAG` с
  назначениями — `Some elements depend on`, нужен `CASCADE`; `DROP FOLDER IF EXISTS …
  CASCADE` удаляет папку с содержимым (уточнение к вводной из T2: `IF EXISTS` не помогает,
  `CASCADE` — да); `CREATE OR REPLACE FOLDER` без `DESCRIPTION` **стирает** описание
  существующей папки; `ALTER FOLDER … RENAME` переносит папку между родителями,
  `MOVE VIEW` не ломает зависимые представления; описание у папки без `=`, у тега с `=`;
  `GET_DATABASES()` фильтруется по `db_name`, `input_tag_names` в `GET_VIEW_TAGS()` —
  массив. Не проверено (помечено `unverified`): `AUTHENTICATION LDAP`, `VCS`,
  `CREDENTIALS_VAULT`, `DATA_MOVEMENT`, `ALTER FOLDER … COPY` и `MOVE` не-view элементов,
  `CACHE`/`MEMORYCONFIG` в `ALTER DATABASE`. Context7 документации Denodo не содержит;
  страницы VQL Guide 9.5 снимались напрямую (accessible-версия, обычная обрезается
  оглавлением).
- **T6. Ядро `/denodo:vql`.** `skills/vql/SKILL.md`: рабочий цикл (VQL в файл проекта,
  инлайн `-e` — только для чтения, запрет на пробные объекты, один файл применяется целиком),
  конвенции именования и слоёв с переопределением через `.denodo/conventions.md`,
  идемпотентность и правило безопасности «создаёшь сам — разрушаешь после подтверждения»
  с разбором HTTP по методу и пути, таблицей рационализаций и красными флагами, плюс карта
  навыков. Писался по TDD для документации: пять сценариев субагентами без ядра и с ядром.
  Базовые провалы — DDL инлайном через `-e` с пятью мусорными объектами на сервере и
  выдуманным `IF NOT EXISTS`; удаление двух тегов маркетплейса и `tags/vdp/synchronize`
  без единого вопроса человеку; `CREATE` на профиле `production: true` молча; полное
  игнорирование `.denodo/conventions.md` в корне проекта. С ядром все пять проходят.
  Дефолт конвенций взят из официального документа Denodo «VDP Naming Conventions», а не
  придуман; единственное добавление плагина — `wr_` для wrapper'а.
  Проверено на стенде 9.5.1 (2026-09-09), потому что от этих фактов зависят правила ядра:
  `CREATE OR REPLACE DATABASE` **сохраняет содержимое базы** (агент без ядра предполагает
  обратное и заводит отдельный bootstrap-файл), `IF NOT EXISTS` не существует
  (`Syntax error … near 'IF'`), папки-слои с цифрой, пробелами и дефисом парсер принимает,
  путь папки регистронезависим, вложенная папка требует существующего родителя,
  `CREATE OR REPLACE VIEW` поверх звена цепочки не ломает зависимые представления.
  По итогам прогонов уточнено правило прода: read-only (`env check`, `DESC`, `SELECT`)
  разрешён и там, подтверждения требует любое изменение — буквальное «на проде подтверждается
  всё» запрещало агенту даже посмотреть, куда он подключён.

- **T7. Навык `/denodo:execute`.** `skills/execute/SKILL.md` (команды, чтение JSON-ответа,
  действия по `error.kind`, сценарий «нет профиля» через `! … env init`, правило
  `--allow-destructive` только после подтверждения человека с таблицей рационализаций,
  верификация после применения) и `references/errors.md` — два класса: тексты VDP по
  подстрокам (46 случаев сняты со стенда 9.5.1) и HTTP-статусы маркетплейса с `code`,
  плюс клиентские `error.kind`. Навык писался по TDD для документации: базовый прогон без
  навыка показал, что агент сам ставит `--allow-destructive` на production-профиле
  («пользователь назвал файл», «DROP IF EXISTS — no-op», «база тестовая»); с навыком все
  три сценария (нет профиля, production, ошибка в середине файла) проходят. Побочно:
  `FOLDER '/x'` без `=` даёт `Syntax error near '''`, `DESC TABLE` не существует,
  `--type folder` требует путь в кавычках. Язык — английский, русские триггеры — вопрос T6/T9.
- **T5. Слой исполнения `scripts/denodo`.** Launcher на stdlib (`DENODO_CLI_PYTHON` →
  `uv run --script` → venv в данных плагина → JSON с командой установки), пакет
  `scripts/denodo_cli` с профилями (`~/.denodo/profiles.toml`, формат зафиксирован в 7.4
  спеки), разбиением VQL на выражения, двумя транспортами (`vql_psycopg2`, `api_rest`),
  командами `vql run|desc`, `api`, `env list|check|init` и JSON-выводом с кодами выхода.
  141 юнит-тест без зависимостей, 8 интеграционных на стенде 9.5.1. Закрыт открытый вопрос
  T2 §3.5: при ошибке в середине строки с `;` сервер выполняет всё до неё и ничего после,
  без отката; клиент режет файл сам и сообщает индекс упавшего выражения. Разрушительные
  операции помечаются по правилу 6.3 (VQL — по ключевому слову, HTTP — по методу и пути)
  и на production-профиле требуют `--allow-destructive`. `verify` отложен до T12.
- **T11. Спайк: API Data Marketplace.** Риск №2 снят: пути и тела для тегов, категорий
  и external elements сняты с OpenAPI живого сервера и подтверждены на стенде;
  аутентификация — HTTP Basic учёткой VDP, `serverId` необязателен при одном сервере.
  Импортированные из VDP теги в маркетплейсе только на чтение — подтверждено (`403` на
  правку и назначение). External element в 9.5 не создаётся напрямую: он импортируется из
  interface view VDP через custom external tool server. Найдены разрушительные вызовы без
  `DROP`/`DELETE` в тексте (`tags/vdp/synchronize` с неполным списком стирает остальные
  импорты) и ловушка VQL (`one` — зарезервированное слово). Скрипт —
  `spikes/t11_marketplace_api.py` (121 шаг, 0 расхождений на 9.5.1), отчёт —
  [отчёта T11](superpowers/specs/2026-09-08-spike-t11-marketplace-api.md). Вводные разнесены по T5, T6, T7, T8c, T8d.
- **T2. Спайк: DDL через канал 9996.** Риск №1 снят: через `denodo+psycopg2` прошла
  вся VQL-цепочка v1 от базы до ассоциации, `CREATE OR REPLACE` и `DROP ... IF EXISTS`
  подтверждены для девяти типов, `api_rest` нужен только маркетплейсу. Скрипт —
  `spikes/t2_ddl_over_9996.py` (89 шагов, 0 расхождений на 9.5.1), отчёт —
  [спайк T2](superpowers/specs/2026-09-08-spike-t2-ddl-over-9996.md). Побочно
  найдены четыре ловушки клиента (автокоммит, `%`, `CONNECT DATABASE`, `text()`) и три
  ловушки VQL (парный `REMOVE_FROM` у тега, полный `OUTPUTSCHEMA` у wrapper DF,
  `TIMETOLIVEINCACHE` перед `ADD SEARCHMETHOD`) — разнесены по вводным T5, T7, T8a–T8c.
- **T4. Каркас плагина.** `.claude-plugin/plugin.json` (плагин `denodo`, версия 0.1.0) и
  `.claude-plugin/marketplace.json` (маркетплейс `denodo-skills`, один плагин с
  `source: "./"`). Проверено на локальной установке: `claude plugin validate .` проходит
  в `--strict`, плагин ставится, а навык из `skills/vql/` виден как `denodo:vql` —
  namespace плагин добавляет сам, инвариант «без префикса `denodo-` в именах директорий»
  подтверждён на практике. Установка с GitHub проверяется после мерджа в `main`.
- **T1. Перечень объектов v1.** Шестнадцать объектов в четырёх навыках и двух каналах,
  с командами, способом верификации каждого и порядком сборки — см.
  [объём v1](superpowers/specs/2026-09-04-denodo-v1-scope.md). В дизайн-документ внесены
  следствия: `/denodo:marketplace` в карте навыков и структуре репозитория, формат навыка
  отвязан от VQL, верификация распространена на HTTP-шаблоны, зафиксирован дефолт
  идемпотентности, добавлен риск №2.
- Дизайн проекта: выбор «навыки, а не MCP-сервер», архитектура, слой исполнения, формат
  навыков, верификация, границы v1 — см. дизайн-документ.
