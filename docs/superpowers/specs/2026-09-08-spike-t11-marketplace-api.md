# Спайк T11: API Data Marketplace

**Дата:** 2026-09-08
**Статус:** закрыт, риск №2 снят
**Стенд:** Denodo Platform 9.5.1 в контейнере, Data Marketplace того же образа на порту 9090
(контекст-путь `/denodo-data-catalog`, историческое имя сохранено), один
зарегистрированный сервер VDP; пользователь с правами администратора
**Скрипт:** `spikes/t11_marketplace_api.py` — `uv run spikes/t11_marketplace_api.py --env dev`,
профиль из `~/.denodo/profiles.toml`, VDP-часть через `denodo+psycopg2` как в T2, REST — на
стандартной библиотеке. Всё создаётся с префиксом `t11_` в базе `denodo_skills_test` и
удаляется в конце, включая копии в маркетплейсе. Финальный прогон: 121 шаг, 0 расхождений
с ожиданием.
**Источники сверх стенда:** OpenAPI 3.0.1 с самого сервера (`/v3/api-docs`, 375 путей,
465 операций — сохранён только на время спайка, в репозиторий не входит) и три страницы
документации 9.5: REST API, «Tags», «Set Up Custom External Tool».

---

## 1. Ответ на вопрос спайка

**Все три объекта `marketplace` доступны через `/public/api/…` под HTTP Basic, но
external element — не объект, который создаётся одним вызовом.** Теги и категории —
обычный CRUD с числовыми идентификаторами. External element в 9.5 *импортируется*:
маркетплейс сам читает interface view в VDP, зарегистрированное как custom external tool
server, и по `POST …/synchronize` создаёт, обновляет и удаляет элементы. Прямого
`POST /external-elements` в API нет — есть только правка имени, описания и свойств уже
импортированного элемента.

Следствие для навыка `marketplace`: шаблон «external element» — это цепочка из пяти
вызовов и одного VQL-фрагмента (раздел 5), а не один HTTP-вызов. Раздел 8 спеки это
допускает («минимальный шаблон — VQL либо HTTP-вызов»), но шаблон external element
оказывается **и тем, и другим**.

Утверждение документации, на котором держится развилка `catalog` ↔ `marketplace`,
подтверждено на стенде: импортированный из VDP тег в маркетплейсе только на чтение
(раздел 3.3).

## 2. Аутентификация и адресация — что нужно транспорту `api_rest` (T5)

| Проверка | Результат |
|---|---|
| Без креденшелов | `401`, `WWW-Authenticate: Basic realm="Denodo"`; `/Ping` открыт |
| HTTP Basic тем же пользователем VDP, что в профиле | работает на всех вызовах спайка; отдельной учётки маркетплейса нет |
| `serverId` не передан | работает — сервер один; список серверов и их `id` — `GET /public/api/configuration/servers` |
| `serverId` неверный | `401 {"code":"AUTHENTICATION_SERVER_NOT_FOUND"}` — ошибка классифицируется как аутентификационная, не как «не найдено» |
| `uri=//host:9999/admin` вместо `serverId` | эквивалентно; в шаблонах не нужен |
| Заголовки stateless-ответа | **каждый** ответ несёт `Set-Cookie: JSESSIONID=…` — сервер заводит сессию на любой Basic-вызов |
| OAuth stateless / stateful | по документации выключены по умолчанию (`oauth.statelessEnabled=false`), на стенде не пробовались |

**Решение для `scripts/denodo`:** HTTP Basic на каждом запросе, без cookie-jar. Это
единственный способ, включённый по умолчанию, и он не требует ни VDP с OAuth, ни
хранения `X-XSRF-TOKEN`. `serverId` — необязательное поле профиля; если оно не задано,
параметр не передаётся. Сессии, которые сервер заводит на каждый вызов, — цена
stateless-режима; если в T5 выяснится, что они мешают (утечка сессий при `verify` на
сотни вызовов), можно возвращать `JSESSIONID` обратно — но это уже stateful, и его
нужно проверять отдельно.

**Профиль среды** (раздел 7.4 спеки оставляет формат плану реализации). Рабочий
вариант, с которым шёл спайк, плюс одно поле:

```toml
[dev]
host = "localhost"          # VDP
port = 9996
database = "admin"
user = "…"
password = "…"
production = false
marketplace_url = "http://localhost:9090/denodo-data-catalog"   # без него api_rest недоступен
# marketplace_server_id = 1                                      # только при нескольких VDP
```

Учётка одна на оба сервера: маркетплейс аутентифицирует пользователей VDP. Отдельные
`marketplace_user`/`marketplace_password` не нужны, пока не встретится стенд, где это не так.

**Формат ошибок** — один на весь API, годится для `references/errors.md` (T7):

```json
{"code": "SERVER_DUPLICATED", "message": "Server with name '…' already exists.",
 "status": "CONFLICT", "subErrors": null, "timestamp": "08-09-2026 05:00:23"}
```

Но не всегда: `409` на дубликат тега, категории, типа приходит **с пустым телом**, `403`
на импортированный тег — тоже пустой, а ошибка привязки пути (`viewId=None`) — Spring
`problemDetail` без `code`. Транспорт обязан отдавать навыку HTTP-статус отдельно от
тела, и справочник ошибок строится по статусу, а по `code` — только когда он есть.

## 3. Теги маркетплейса

### 3.1 Вызовы, подтверждённые на стенде

| Действие | Вызов | Тело | Ответ |
|---|---|---|---|
| Создать | `POST /public/api/tags` | `{"name","description","descriptionType":"TEXT"}` — все три обязательны | `200` + объект с `id`, `vdpTag:false` |
| Дубликат имени | тот же | | `409`, пустое тело |
| Найти по имени | `GET /public/api/tags` (все) или `GET /public/api/tag-management/tags?offset=0&limit=N&nameFilter=…` | | список / `{"count","elements":[…]}` |
| Обновить | `PUT /public/api/tags` | `{"id","name","description","descriptionType"}` | `200` |
| Назначить представлениям | `POST /public/api/tags/{tagId}/views` | `[viewId, …]` | `200` + **список id, которые назначить не удалось** |
| Снять | `DELETE /public/api/tags/{tagId}/views/{viewId}` | | `200` |
| Кому назначен | `GET /public/api/tags/{tagId}/elements` | | `{"views":[…],"webservices":[…]}` |
| Удалить | `DELETE /public/api/tags/{tagId}` | | `200` |
| Удалить повторно | тот же | | `500 {"code":"GENERIC","message":"Incorrect number of deleted tuples"}` |

Назначить тег можно и с другой стороны — `POST /public/api/views/{viewId}/tags?tagsId=…`
заменяет весь набор тегов представления. Для шаблона «навесить тег» правильнее
`tags/{tagId}/views`: он добавляет, а не заменяет.

### 3.2 Ловушки

- **`POST …/views` не считает несуществующий id ошибкой.** `[999999999]` → `200` и
  `[999999999]` в ответе. Повторное назначение уже назначенного → `200` и `[viewId]`
  (тоже «не удалось»). Успех — это **пустой список** в ответе, а не `200`.
- **Имя — не ключ.** Все операции идут по числовому `id`, который выдаётся при создании
  и различается между инсталляциями. Шаблон не может содержать `id`; навык обязан сначала
  найти объект по имени (`GET` списка + фильтр), а потом вызывать `PUT`/`DELETE`.
  Идемпотентный «создать или обновить» — это `GET` → `POST` либо `PUT`, двух вызовов
  не избежать.
- **`viewId` существует только у синхронизированного представления.**
  `GET /public/api/view-details?databaseName=…&viewName=…` отвечает и до синхронизации
  каталога (`inVDP:true`, читает VDP вживую), но `id:null, inLocal:false`. Назначить тег
  или категорию такому представлению нельзя. После
  `POST /public/api/element-management/all/synchronize {"proceedWithConflicts":"SERVER"}`
  (ответ — diff: `inserted/modified/removed` по базам, представлениям, веб-сервисам)
  `id` появляется. На стенде с четырьмя базами это 0,5–2 с; на большом каталоге —
  неизвестно, транспорту нужен длинный таймаут.

### 3.3 Импортированные теги VDP — только на чтение, подтверждено

| Проверка | Результат |
|---|---|
| `GET /public/api/tags/vdp` | теги VDP читаются вживую, без синхронизации каталога |
| `POST /public/api/tags/vdp/synchronize {"vdpTags":[…]}` | импорт; в `GET /tags` тег получает `vdpTag:true` |
| `PUT /tags` на импортированный | `403`, пустое тело |
| `POST /tags/{id}/views` на импортированный | `403` |
| `DELETE /tags/{id}` на импортированный | `500 "Incorrect number of deleted tuples"`, тег остаётся |
| Назначение, сделанное в VQL (`ALTER TAG … ADD_TO`) | видно в `GET /views/{viewId}/tags` после импорта |
| Повторный импорт того же тега | без дубликата, но **`id` меняется** — копия пересоздаётся |

**Ловушка, найденная спайком, — разрушительная.** `tags/vdp/synchronize` трактует
список в теле как *полный* набор импортированных тегов: импорт одного тега на стенде
**удалил** ранее импортированный чужой тег (второй прогон); восстановил его только вызов
с полным списком из `GET /tags/vdp`. Навык обязан всегда передавать полный список, а
правило безопасности ядра (6.3) — считать этот вызов разрушительным, хотя в нём нет ни
`DROP`, ни `DELETE`.

Уборка: `DROP TAG` в VDP отказывает, пока тег назначен (`Some elements depend on`), но
после `DROP DATABASE` проходит — зависимость уходит с базой. Копия в маркетплейсе
исчезает после `tags/vdp/synchronize` с актуальным списком; `GET /tags/vdp/changes`
показывает, что маркетплейс считает расхождением (`inLocal`, `nameConflict`).

## 4. Категории

| Действие | Вызов | Тело | Ответ |
|---|---|---|---|
| Создать | `POST /public/api/category-management/categories` | `{"name","description","descriptionType","parentId"?}` | `200` + объект с `id`, `parentId`, `path` |
| Дубликат имени | тот же | | `409`, пустое тело |
| Дерево | `GET …/categories/tree` | | вложенный список `children` |
| Обновить | `PUT …/categories/{id}` | `{"name","description","descriptionType"}` — `parentId` можно не передавать | `200` |
| Назначить представлениям | `POST …/categories/{id}/views` | `[viewId, …]` | `200` + список неназначенных, как у тегов |
| Снять | `DELETE …/categories/{id}/views?elementIds=…` | | `200` |
| Удалить | `DELETE …/categories/{id}` | | `200` |

Две особенности против тегов:

- **Удаление родителя каскадно удаляет потомков, без ошибки и без подтверждения.**
  Для правила 6.3 — самая разрушительная операция раздела.
- **Повторный `DELETE` — `200`**, а не ошибка. Удаление категорий идемпотентно, удаление
  тегов — нет (раздел 3.1). Справочник ошибок не может обобщать «повторное удаление → 500».

## 5. External elements — процедура из пяти шагов

Все пять шагов подтверждены на стенде в этом порядке.

| Шаг | Вызов | Тело | Ответ |
|---|---|---|---|
| 1. Тип элемента | `POST /public/api/external-elements-types` | `{"name","description","visualName","iconKey","iconColorCode","reversedIconColorCode"}` — все обязательны, `iconKey` — ключ FontAwesome | `201` + `externalElementTypeId`; дубликат `name` → `409` |
| 2. Тип провайдера | `POST /public/api/external-providers-types`, **multipart** | часть `request` (`application/json`: `{"name","visualName"}`) + часть `icon` (svg/png) | `201` + `externalProviderTypeId`; дубликат → `409` |
| 3. Сервер | `POST /public/api/external-tool-servers` | `{"type":"CUSTOM","name","description"?,"externalProviderTypeId","databaseName","viewName"}` | `200` + объект с `id`; interface view на этот момент может не существовать; дубликат имени → `409 SERVER_DUPLICATED` |
| 4. Контракт | `GET /public/api/external-tool-servers/{id}/vql-metadata` | | `200`, **JSON-строка** с VQL (`Content-Type: application/json`) |
| 5. Синхронизация | `POST /public/api/external-tool-servers/synchronize` | `{"externalToolServerIds":[id]}` | `200` + diff по серверам: `externalElementsAdded/Updated/Deleted` |

VQL из шага 4 применился без правок (два `CREATE OR REPLACE TYPE` и
`CREATE OR REPLACE INTERFACE VIEW` с колонками `id, name, description,
external_element_type, url, created_at:timestamp, updated_at:timestamp,
associations:<array>`). Первая строка — `CONNECT DATABASE`; при соединении прямо в
нужную базу её нужно пропустить (отчёт T2, 3.4).

**Реализация interface view — часть шаблона, и это VQL.** Рабочий минимум из спайка:

```sql
CREATE OR REPLACE VIEW t11_ext_flat AS SELECT
    't11.element.1' AS id, 'T11 spike element' AS name, '…' AS description,
    'T11_TEST_TYPE' AS external_element_type, 'https://example.invalid/t11' AS url,
    TO_TIMESTAMP('yyyy-MM-dd HH:mm:ss', '2026-09-08 10:00:00') AS created_at,
    TO_TIMESTAMP('yyyy-MM-dd HH:mm:ss', '2026-09-08 10:00:00') AS updated_at,
    'denodo_skills_test.t11_view' AS associated_element_id,
    CAST('text', NULL) AS external_tool_server_name,
    'VIEW' AS associated_element_type, 'OUT' AS direction, 'implemented_by' AS role
FROM DUAL();

CREATE OR REPLACE VIEW t11_ext_elements AS SELECT
    id, name, description, external_element_type, url, created_at, updated_at,
    NEST(associated_element_id, external_tool_server_name, associated_element_type, direction, role) AS associations
FROM t11_ext_flat
GROUP BY id, name, description, external_element_type, url, created_at, updated_at;

ALTER INTERFACE VIEW i_t11_elements SET IMPLEMENTATION t11_ext_elements;
```

Что здесь важно:

- `external_element_type` — это `name` из шага 1, строка-в-строку.
- Массив ассоциаций собирается `NEST(...)` с `GROUP BY` по остальным колонкам;
  литерального конструктора массива в проекции нет.
- `NULL` в типизированной колонке — `CAST('text', NULL)`; синтаксис `CAST` в VQL —
  `CAST('тип', выражение)`.
- Ассоциация с представлением: `associated_element_id = 'база.представление'`,
  `external_tool_server_name = NULL`, тип `VIEW`, направление `IN`/`OUT`, `role` — текст
  на ребре 360-графа. Если представления нет, синхронизация отказывает целиком:
  `400 INVALID_VDP_EXTERNAL_ELEMENT_METADATA "Invalid association for element with id
  '…'. The view '…' does not exist"` (первый прогон, представление тогда не создалось).
- Слово `one` — зарезервировано: `SELECT 1 AS one FROM DUAL()` не проходит парсер.
  Ловушка для любого шаблона с алиасами (T8b, T8c).

После синхронизации:

| Проверка | Результат |
|---|---|
| Поиск по имени: `POST /public/api/search/external-elements/metadata` с `{"text","whereToSearchList":["ELEMENT_NAME"],"searchType":"EXACT_MATCH","offset","limit", остальные фильтры — пустые списки и `false`}` | `{"elements":[{id, name, typeName, originalExternalElementId, externalToolServerName, tags, categories, …}],"elementsCount"}`; `originalExternalElementId` — наш `id` из view |
| `GET /public/api/external-elements/{id}/details` | полная карточка; `url` попал в автоматически созданную группу атрибутов `<тип>_default` |
| Тег: `POST /public/api/tags/{tagId}/external-elements [id]`, категория: `POST …/categories/{catId}/external-elements [id]` | `200`; обратные `GET …/external-elements` их показывают |
| `PUT /public/api/external-elements/{id}/description` | `200` — правка на стороне маркетплейса |
| Повторная синхронизация без изменений в view | diff пустой; тег, категория и правленое описание **сохраняются** — маркетплейс не перезаписывает то, у чего `updated_at` не сдвинулся |
| `DELETE /public/api/external-tool-servers/{id}` | `200`; **все его элементы исчезают** вместе с назначениями; повторно → `404` |
| `DELETE /external-providers-types/{id}`, `DELETE /external-elements-types/{id}` | `200` после удаления сервера; повторно → `404` |

Списки `GET /public/api/external-tool-servers` **не** возвращают `databaseName`/`viewName`
— только `GET …/{id}`. Сопоставлять сервер с шаблоном придётся по имени.

## 6. Что нужно ядру и навыку `marketplace` (T6, T8d)

**Правило безопасности 6.3 должно строиться по методу и пути, а не по словам.** Список
разрушительных вызовов, подтверждённых спайком, — ни в одном нет `DROP`:

| Вызов | Что теряется |
|---|---|
| `DELETE /public/api/tags/{id}`, `DELETE /public/api/tags/delete-multiple` | тег и все его назначения |
| `DELETE /public/api/category-management/categories/{id}` (и `?categoryIds=`) | категория **и все потомки** |
| `DELETE /public/api/external-tool-servers/{id}` | сервер и **все импортированные им элементы** с тегами и категориями |
| `POST /public/api/tags/vdp/synchronize` с неполным списком | все импортированные теги VDP, не попавшие в список |
| `POST /public/api/element-management/all/synchronize` с `proceedWithConflicts:"SERVER"` | локальные правки описаний в маркетплейсе там, где VDP расходится |
| `POST /public/api/views/{viewId}/tags?tagsId=`, `POST …/views/{id}/categories?categoriesId[]=` | прежние назначения представления — «set», не «add» |

**Идемпотентность (6.4) для HTTP.** `CREATE OR REPLACE` здесь соответствует паре
«найти по имени → `POST` или `PUT`»; `DROP … IF EXISTS` — «найти по имени → `DELETE`,
если найден». Повторный `DELETE` у тегов — `500`, у категорий — `200`, у типов и серверов
— `404`; полагаться на статус повторного удаления нельзя, только на предварительный
поиск.

**Формат шаблона.** Для тега и категории — HTTP-вызов с телом; для external element —
последовательность из пяти HTTP-вызовов и VQL-фрагмента, в которой шаги 1–3
выполняются один раз на тип элементов, а шаги 4–5 — на каждый источник. Пометка
`verified:` у такого шаблона относится ко всей цепочке.

## 7. Тексты ошибок для `references/errors.md` (T7)

| HTTP | Тело | Когда |
|---|---|---|
| `401` | `{"status":401,"error":"Unauthorized","path":…}` (Spring) | нет заголовка `Authorization` |
| `401` | `{"code":"AUTHENTICATION_SERVER_NOT_FOUND","message":"Authentication error: Server not found"}` | неверный `serverId` |
| `403` | пусто | правка или назначение импортированного тега VDP |
| `404` | пусто | `DELETE` несуществующего сервера или типа |
| `409` | пусто | дубликат имени тега, категории, типа элемента, типа провайдера |
| `409` | `{"code":"SERVER_DUPLICATED","message":"Server with name '…' already exists."}` | дубликат имени external tool server |
| `400` | `{"code":"INVALID_VDP_EXTERNAL_ELEMENT_METADATA","message":"Invalid association for element with id '…'. The view '…' does not exist"}` | ассоциация на несуществующее представление при синхронизации |
| `400` | `{"code":"INVALID_EXTERNAL_TOOL_SERVER","message":"The provided external tool server with id '…' is invalid"}` | `…/changes` у CUSTOM-сервера — эндпоинт только для Tableau/Power BI |
| `400` | Spring `problemDetail` с `MethodArgumentTypeMismatchException` | нечисловой id в пути (например, `None`) |
| `500` | `{"code":"GENERIC","message":"Incorrect number of deleted tuples"}` | `DELETE` уже удалённого или импортированного тега |
| `500` | `{"code":"GENERIC","message":"Cannot invoke \"java.lang.Long.longValue()\" because \"elementId\" is null"}` | `null` в списке id тела |
| `500` | `{"code":"GENERIC","message":"Error executing query… Database doesn't exist."}` | `view-details` по несуществующей базе |

## 8. Что спайк не покрыл

- OAuth в обоих режимах и stateful-сессии (`/login`, `X-XSRF-TOKEN`): на стенде OAuth
  не включён. Basic закрывает v1.
- Несколько зарегистрированных VDP: `serverId` проверен только как «верный/неверный» при
  одном сервере.
- Поведение под ограниченной ролью: документация называет права «create/delete for
  Elements», «Servers Administration», «Synchronize» — на стенде всё шло под
  администратором.
- Обновление external element через сдвиг `updated_at` и ассоциации типа
  `EXTERNAL_ELEMENT`; веб-сервисы как цель тегов и категорий; пользовательские свойства.
- Нужна ли синхронизация каталога для представления-цели ассоциации, или достаточно
  его существования в VDP: в удачных прогонах каталог был синхронизирован до
  `synchronize` сервера.
- Время `element-management/all/synchronize` на каталоге в сотни представлений.
- Порядок удаления: тип провайдера и тип элемента удалялись после сервера; отказ при
  обратном порядке не проверялся.
