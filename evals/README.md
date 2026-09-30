# Eval-сьют: срабатывает ли нужный навык

Сьют отвечает на один вопрос — **выбирает ли агент правильный навык по фразе человека**.
Он не проверяет, что навык делает дальше: ни VQL, ни обращений к стенду здесь нет.
Исполнение проверяют [верификация шаблонов](../scripts/denodo) и юнит-тесты, срабатывание
— только этот сьют.

Зачем он нужен, написано в разделе 11.2 [дизайн-документа](../docs/superpowers/specs/2026-09-04-denodo-skills-design.md):
описания навыков конкурируют между собой, и когда после v1 добавятся новые, деградация
старых пройдёт незаметно. Отсюда правило: **любая правка `description` — повод прогнать
сьют**, даже если правка косметическая.

## Прогон

```
claude plugin eval . --ablation none
```

Из корня репозитория; плагин резолвится по пути, устанавливать его для этого не нужно.
Полезные флаги: `-j 4` — четыре прогона параллельно, `--runs 1` — быстрая обкатка вместо
трёх заходов, `--tag discrimination` или `--case 'discrimination-*'` — подмножество,
`--no-publish` — не выкладывать HTML-отчёт. Результаты ложатся в `evals/results/`
(в `.gitignore`).

### Контрольный прогон на установленном плагине

Прогон по пути читает навыки из `skills/` рабочего дерева. Раз в веху стоит проверить и то,
что описания срабатывают у **установленного** плагина — из кэша, а не из репозитория:

```
claude plugin marketplace add ./          # из корня репозитория, форма пути обязательно с ./
claude plugin install denodo@denodo-skills
cd /tmp && claude plugin eval denodo@denodo-skills --runs 1 --ablation none
```

Запускать намеренно **не** из репозитория: так видно, что плагин резолвится по имени, а не
подхватывается из текущей директории. Кэш — снимок на момент установки, а не живое дерево,
поэтому после правок навыков нужен `claude plugin update denodo`. Убрать за собой:
`claude plugin uninstall denodo` и `claude plugin marketplace remove denodo-skills`.

`--ablation none` стоит здесь осознанно. По умолчанию прогон добавляет арм «без плагина»
и считает дельту — но для сьюта о срабатывании навыков этот арм проверяет тавтологию
(без плагина навык не сработает) и удваивает стоимость.

## Устройство кейса

Кейс — это директория с `prompt.md` (фраза плюс frontmatter) и `graders/*.md` (по файлу на
проверку, имя файла становится именем грейдера).

Все грейдеры здесь одного типа — `tool_used` с `tool: Skill`, то есть детерминированные:
они читают трассу прогона и считают вызовы, без LLM-судьи и без денег на его вызов.
Различает навыки поле `input_match` — регексп по входу вызова, где лежит `{"skill":
"denodo:catalog"}`. Отсюда две формы:

| форма | смысл |
|---|---|
| `input_match: "denodo:views"` | навык обязан сработать (`min` по умолчанию 1) |
| `input_match: "denodo:views"` + `min: 0`, `max: 0` | навык обязан **не** сработать |

`min: 0` в отрицательной форме обязателен: без него `min` остаётся равен единице и условие
становится «от 1 до 0», то есть невыполнимым.

Frontmatter кейса задаёт `runs: 3` (три захода, чтобы разовая случайность не читалась как
регрессия), `max_turns`, `allowed_tools` и `append_system_prompt`. Последний сообщает
агенту, что песочница пуста: без этого он уходит искать по файловой системе несуществующие
файлы проекта и сжигает лимит ходов раньше, чем доходит до предметного навыка — прогон
тогда меряет разведку, а не маршрутизацию.

## Две группы

**`routing`** — по одной однозначной фразе на каждый из шести навыков. Ловит полную
поломку: навык перестал срабатывать вообще. Эти кейсы **не запрещают** попутный вызов
`/denodo:vql`: он точка входа и карта остальных навыков, обратиться к нему по дороге
нормально.

Two more routing cases guard the half of `datasources` that creates nothing itself: a REST API
(`routing-datasources-rest-api`) and a base view out of date with its source
(`routing-datasources-schema-drift`). The skill sends both to Design Studio, and it can only
do that if its description still fires on them.

`routing-vql-expression` guards the table of silent expression deltas in `/denodo:vql`: a
question about writing the expressions of a `SELECT` — a substring, a month label, a time
difference — creates no object, so no object skill owns it, and the table only helps if
`vql` fires on it. It passed on the descriptions as they were when the table was added (T24);
no description was changed for it.

`routing-views-union` guards the union half of `/denodo:views` (T25): combining views of one
entity from several sources, with a one-source query reading one source, is a derived view,
and the phrase names no view type at all.

Three more guard the checks `/denodo:views` runs around a view rather than the view itself
(T26): whether a column can go and what uses it (`routing-views-column-impact`), where a field
comes from (`routing-views-lineage`), and whether a mart over a database runs in the database
(`routing-views-delegation`). None of the three asks for anything to be created, so without
them a description could lose these phrases and every other case would stay green.

Two guard `/denodo:cache` (T27): putting a full cache on a view and loading it
(`routing-cache`), and a cached view that returns no rows or every row twice
(`routing-cache-empty-view`) — the second names no statement, only the symptom, which is how
the silent failures of a full cache reach a human.

Two guard `/denodo:semantics` (T28): describing the undocumented views of a database for an AI
assistant (`routing-semantics`), and an agent that does not see a view through the Denodo MCP
Server (`routing-semantics-mcp-visibility`) — the second names neither a tag nor a statement,
only the symptom, and the cause is a VDP tag the MCP Server is configured with.

**`discrimination`** — фразы на границах, где описания конкурируют. Каждый такой кейс несёт
и положительный, и отрицательный грейдер, потому что проверяется именно выбор между двумя:

| кейс | ждём | и запрещаем |
|---|---|---|
| `discrimination-tag-vdp` | `catalog` | `marketplace` |
| `discrimination-tag-marketplace` | `marketplace` | `catalog` |
| `discrimination-base-view` | `datasources` | `views` |
| `discrimination-derived-view` | `views` | `datasources` |
| `discrimination-author-not-run` | `views` или `vql` | `execute` |
| `discrimination-run-not-author` | `execute` | предметные навыки |
| `discrimination-procedure-base-view` | `datasources` | `procedures` |
| `discrimination-json-array` | `views` | `datasources` |
| `discrimination-impact-not-procedures` | `views` | `procedures` |
| `discrimination-cache-not-views` | `cache` | `views` |
| `discrimination-semantics-not-views` | `semantics` | `views` |
| `discrimination-semantics-not-marketplace` | `semantics` | `marketplace` |

Первые две строки — тот самый риск, ради которого сьют и заводился: «тег» в VDP и «тег» в
маркетплейсе — **разные объекты на разных серверах**, и перепутанный навык уйдёт корректным
вызовом не туда.

## Как читать падение

Счёт кейса — доля прошедших грейдеров, усреднённая по заходам; `--threshold` по умолчанию
1.0, так что любой промах роняет прогон. Упавший кейс — это одно из двух, и различать их
надо до правки:

- **описания разошлись** — правится `description` навыка, после чего сьют гоняется заново;
- **кейс кривой** — фраза двусмысленна или грейдер запрещает законное поведение; правится
  кейс.

Что именно произошло, видно в трассе. Путь к ней печатает `aggregate-result.json`
(`arms.with[].tracePath`), а `--keep-temp` сохраняет песочницу прогона целиком; в трассе
лежат все вызовы инструментов по порядку, включая то, какой навык сработал вместо
ожидаемого.
