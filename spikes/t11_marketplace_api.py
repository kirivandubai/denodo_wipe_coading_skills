# /// script
# requires-python = ">=3.11"
# dependencies = ["denodo-sqlalchemy>=2.0.5", "psycopg2-binary>=2.9.6"]
# ///
"""Спайк T11: API Data Marketplace — теги, категории, external elements через REST.

Запуск:  uv run spikes/t11_marketplace_api.py --env dev [--marketplace-url http://host:9090/denodo-data-catalog]
Профиль берётся из ~/.denodo/profiles.toml (или $DENODO_PROFILES); креденшелы в
аргументах не передаются. Маркетплейс аутентифицирует тем же пользователем VDP, что и
профиль. Всё создаётся с префиксом t11_ в базе denodo_skills_test и удаляется в конце.
Результаты прогона — docs/superpowers/specs/2026-09-08-spike-t11-marketplace-api.md.

Что проверяется, по шагам:
  1. Аутентификация: без креденшелов, HTTP Basic, параметр serverId (верный, неверный,
     отсутствующий), заголовки ответа (сессионная кука при stateless-вызове).
  2. Синхронизация каталога: новая база и представление VDP появляются в маркетплейсе
     только после POST element-management/all/synchronize; как получить viewId.
  3. Теги маркетплейса: создание, дубликат, обновление, назначение представлению,
     снятие, удаление, повторное удаление.
  4. Теги VDP в маркетплейсе: импорт через tags/vdp/synchronize, попытки изменить,
     назначить и удалить импортированный тег — подтверждение «только на чтение».
  5. Категории: создание, дубликат, вложенная, обновление, назначение, удаление
     родителя с потомком, удаление, повторное удаление.
  6. External elements: тип элемента → тип провайдера (multipart) → custom external
     tool server → VQL контракта с vql-metadata → реализация interface view →
     synchronize → поиск → назначение тега и категории → повторная синхронизация →
     удаление сервера (что происходит с элементами).
  7. Уборка: объекты маркетплейса, тег VDP, база, повторная синхронизация каталога.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import sqlalchemy as sa

TEST_DB = "denodo_skills_test"
TEST_VIEW = "t11_view"
VDP_TAG = "t11_vdp_tag"
MP_TAG = "t11_mp_tag"
MP_CAT = "t11_category"
MP_CAT_CHILD = "t11_category_child"
EXT_TYPE = "T11_TEST_TYPE"
EXT_PROVIDER = "T11_TEST_PROVIDER"
EXT_SERVER = "t11 custom server"
EXT_IFACE = "i_t11_elements"
EXT_ELEMENT_ID = "t11.element.1"
EXT_ELEMENT_NAME = "T11 spike element"
DEFAULT_MP_URL = "http://localhost:9090/denodo-data-catalog"
ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">'
    '<rect width="40" height="40" rx="8" fill="#1F3A5F"/></svg>'
).encode()

results: list[dict] = []


# --- запись исходов -------------------------------------------------------------------

def record(name: str, status: str, detail) -> None:
    if not isinstance(detail, str):
        detail = json.dumps(detail, ensure_ascii=False)
    results.append({"step": name, "status": status, "detail": " ".join(detail.split())[:600]})


def vql(name: str, conn, statement: str, *, expect_error: bool = False):
    """Одно VQL-выражение сырым курсором psycopg2 (см. отчёт T2, раздел 3.2)."""
    try:
        cur = conn.exec_driver_sql(statement)
        rows = cur.fetchall() if cur.returns_rows else None
        record(name, "UNEXPECTED_OK" if expect_error else "ok",
               json.dumps([list(map(str, r)) for r in rows[:3]], ensure_ascii=False) if rows else "")
        return rows
    except Exception as exc:  # noqa: BLE001 — спайк, нужен текст любой ошибки
        record(name, "expected_error" if expect_error else "FAIL", str(exc))
        return None


# --- REST-клиент на stdlib ------------------------------------------------------------

class Marketplace:
    def __init__(self, base_url: str, user: str, password: str):
        self.base = base_url.rstrip("/")
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.server_id: int | None = None

    def call(self, method: str, path: str, *, body=None, params=None, auth: bool = True,
             multipart: dict | None = None, timeout: int = 300):
        """Возвращает (status, parsed_json_or_text, headers). Ошибки HTTP не бросает."""
        query = dict(params or {})
        if self.server_id is not None and "serverId" not in query and auth:
            query["serverId"] = self.server_id
        url = self.base + path + ("?" + urllib.parse.urlencode(query, doseq=True) if query else "")
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = self.auth
        data = None
        if multipart is not None:
            boundary = "----t11" + uuid.uuid4().hex
            chunks = []
            for field, (filename, content, ctype) in multipart.items():
                disp = f'form-data; name="{field}"' + (f'; filename="{filename}"' if filename else "")
                chunks.append(f"--{boundary}\r\nContent-Disposition: {disp}\r\nContent-Type: {ctype}\r\n\r\n".encode()
                              + content + b"\r\n")
            data = b"".join(chunks) + f"--{boundary}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw, status, hdrs = resp.read(), resp.status, dict(resp.headers)
        except urllib.error.HTTPError as err:
            raw, status, hdrs = err.read(), err.code, dict(err.headers)
        text = raw.decode("utf-8", "replace")
        try:
            parsed = json.loads(text, strict=False) if text else None
        except json.JSONDecodeError:
            parsed = text
        return status, parsed, hdrs

    def step(self, name: str, method: str, path: str, *, expect_error: bool = False, **kw):
        """Вызов с записью исхода. 2xx — ok, иначе — ошибка; expect_error переворачивает."""
        t0 = time.monotonic()
        status, parsed, hdrs = self.call(method, path, **kw)
        ok = 200 <= status < 300
        if ok:
            state = "UNEXPECTED_OK" if expect_error else "ok"
        else:
            state = "expected_error" if expect_error else "FAIL"
        detail = {"http": status, "ms": int((time.monotonic() - t0) * 1000)}
        if parsed not in (None, ""):
            detail["body"] = parsed
        record(name, state, detail)
        return status, parsed, hdrs


def load_profile(env: str) -> dict:
    path = Path(os.environ.get("DENODO_PROFILES", "~/.denodo/profiles.toml")).expanduser()
    with path.open("rb") as fh:
        profiles = tomllib.load(fh)
    if env not in profiles:
        sys.exit(f"профиль {env!r} не найден в {path}")
    return profiles[env]


def make_engine(p: dict, database: str) -> sa.Engine:
    url = sa.URL.create("denodo+psycopg2", username=p["user"], password=p["password"],
                        host=p["host"], port=int(p.get("port", 9996)), database=database)
    engine = sa.create_engine(url)

    @sa.event.listens_for(engine, "connect")
    def _autocommit(dbapi_conn, _record):  # автокоммит — только так (отчёт T2, 3.1)
        dbapi_conn.autocommit = True

    return engine


def find_by_name(items, name: str, key: str = "name"):
    for it in items or []:
        if it.get(key) == name:
            return it
    return None


# --- VQL реализации interface view для external elements ------------------------------

EXT_FLAT_VQL = f"""CREATE OR REPLACE VIEW t11_ext_flat AS SELECT
    '{EXT_ELEMENT_ID}' AS id,
    '{EXT_ELEMENT_NAME}' AS name,
    'External element created by the T11 spike' AS description,
    '{EXT_TYPE}' AS external_element_type,
    'https://example.invalid/t11' AS url,
    TO_TIMESTAMP('yyyy-MM-dd HH:mm:ss', '2026-09-08 10:00:00') AS created_at,
    TO_TIMESTAMP('yyyy-MM-dd HH:mm:ss', '2026-09-08 10:00:00') AS updated_at,
    '{TEST_DB}.{TEST_VIEW}' AS associated_element_id,
    CAST('text', NULL) AS external_tool_server_name,
    'VIEW' AS associated_element_type,
    'OUT' AS direction,
    'implemented_by' AS role
FROM DUAL()"""

EXT_NEST_VQL = """CREATE OR REPLACE VIEW t11_ext_elements AS SELECT
    id, name, description, external_element_type, url, created_at, updated_at,
    NEST(associated_element_id, external_tool_server_name, associated_element_type, direction, role) AS associations
FROM t11_ext_flat
GROUP BY id, name, description, external_element_type, url, created_at, updated_at"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True)
    ap.add_argument("--marketplace-url", default=None,
                    help="базовый URL Data Marketplace; по умолчанию marketplace_url из профиля или localhost:9090")
    ap.add_argument("--out", default=None, help="куда сохранить полный JSON результатов")
    args = ap.parse_args()
    profile = load_profile(args.env)
    if profile.get("production"):
        sys.exit("профиль помечен production=true — спайк на нём не запускается")
    mp = Marketplace(args.marketplace_url or profile.get("marketplace_url", DEFAULT_MP_URL),
                     profile["user"], profile["password"])

    # 0. Подготовка VDP: база, представление, тег VDP
    admin = make_engine(profile, profile.get("database", "admin"))
    with admin.connect() as c:
        vql("0 чистый старт: DROP DATABASE IF EXISTS", c, f"DROP DATABASE IF EXISTS {TEST_DB}")
        vql("0 чистый старт: DROP TAG IF EXISTS", c, f"DROP TAG IF EXISTS {VDP_TAG}")
        vql("0 CREATE DATABASE", c, f"CREATE DATABASE {TEST_DB} 'T11 spike'")
    admin.dispose()
    test = make_engine(profile, TEST_DB)
    with test.connect() as c:
        vql("0 CREATE VIEW из DUAL()", c, f"CREATE OR REPLACE VIEW {TEST_VIEW} AS SELECT 1 AS val FROM DUAL()")
        vql("0 CREATE TAG VDP", c, f"CREATE OR REPLACE TAG {VDP_TAG} DESCRIPTION = 'VDP tag created by T11 spike'")

    # 1. Аутентификация и serverId
    st, _, hdrs = mp.step("1 Ping без аутентификации", "GET", "/Ping", auth=False)
    st, body, hdrs = mp.step("1 tags/count без аутентификации — ожидаем 401", "GET", "/public/api/tags/count",
                             auth=False, expect_error=True)
    record("1 заголовки 401", "ok", {k: v for k, v in hdrs.items() if k.lower() in ("www-authenticate", "set-cookie")})
    st, body, hdrs = mp.step("1 tags/count с HTTP Basic, без serverId", "GET", "/public/api/tags/count")
    record("1 заголовки 200 (сессионная кука при stateless-вызове?)", "ok",
           {k: v for k, v in hdrs.items() if k.lower() in ("set-cookie", "content-type")})
    st, servers, _ = mp.step("1 configuration/servers — откуда брать serverId", "GET", "/public/api/configuration/servers")
    server_id = servers[0]["id"] if isinstance(servers, list) and servers else 1
    mp.step("1 tags/count с неверным serverId — ожидаем ошибку", "GET", "/public/api/tags/count",
            params={"serverId": 999999}, expect_error=True)
    mp.step("1 tags/count с параметром uri вместо serverId", "GET", "/public/api/tags/count",
            params={"uri": servers[0]["url"]} if servers else {})
    mp.server_id = server_id  # дальше serverId ставится во все вызовы
    mp.step("1 tags/count с serverId", "GET", "/public/api/tags/count")

    # 2. Синхронизация каталога: видит ли маркетплейс новую базу и представление
    st, view0, _ = mp.step("2 view-details до синхронизации каталога", "GET", "/public/api/view-details",
                           params={"databaseName": TEST_DB, "viewName": TEST_VIEW})
    record("2 до синхронизации: id/inLocal/inVDP", "ok",
           {k: view0.get(k) for k in ("id", "inLocal", "inVDP")} if isinstance(view0, dict) else view0)
    mp.step("2 element-management/all/synchronize (proceedWithConflicts=SERVER)", "POST",
            "/public/api/element-management/all/synchronize", body={"proceedWithConflicts": "SERVER"})
    st, dbs, _ = mp.step("2 local/databases после синхронизации", "GET", "/public/api/database-management/local/databases")
    record("2 тестовая база видна маркетплейсу?", "ok" if find_by_name(dbs, TEST_DB, "databaseName") else "FAIL",
           [d.get("databaseName") for d in dbs] if isinstance(dbs, list) else dbs)
    st, view, _ = mp.step("2 view-details после синхронизации → viewId", "GET", "/public/api/view-details",
                          params={"databaseName": TEST_DB, "viewName": TEST_VIEW})
    view_id = view.get("id") if isinstance(view, dict) else None
    record("2 viewId", "ok" if view_id else "FAIL", {"viewId": view_id, "keys": list(view)[:12] if isinstance(view, dict) else view})

    # 3. Теги маркетплейса
    tag_body = {"name": MP_TAG, "description": "Marketplace tag created by T11 spike", "descriptionType": "TEXT"}
    mp.step("3 POST tags — создание", "POST", "/public/api/tags", body=tag_body)
    mp.step("3 POST tags — тот же name повторно, ожидаем ошибку", "POST", "/public/api/tags", body=tag_body,
            expect_error=True)
    st, tags, _ = mp.step("3 GET tags — найти id по имени", "GET", "/public/api/tags")
    tag = find_by_name(tags, MP_TAG)
    tag_id = tag["id"] if tag else None
    record("3 тег найден, vdpTag=false?", "ok" if tag and not tag.get("vdpTag") else "FAIL", tag)
    mp.step("3 GET tag-management/tags с nameFilter (постраничный поиск)", "GET", "/public/api/tag-management/tags",
            params={"offset": 0, "limit": 10, "nameFilter": MP_TAG})
    mp.step("3 PUT tags — обновление описания", "PUT", "/public/api/tags",
            body={"id": tag_id, "name": MP_TAG, "description": "updated by T11 spike", "descriptionType": "TEXT"})
    mp.step("3 GET tags/{id}", "GET", f"/public/api/tags/{tag_id}")
    mp.step("3 POST tags/{id}/views — назначить представлению", "POST", f"/public/api/tags/{tag_id}/views", body=[view_id])
    mp.step("3 POST tags/{id}/views — повторно (идемпотентно?)", "POST", f"/public/api/tags/{tag_id}/views", body=[view_id])
    mp.step("3 POST tags/{id}/views с несуществующим viewId — 200 и список неназначенных id", "POST",
            f"/public/api/tags/{tag_id}/views", body=[999999999])
    st, vtags, _ = mp.step("3 GET views/{viewId}/tags — тег виден на представлении?", "GET",
                           f"/public/api/views/{view_id}/tags")
    record("3 назначение подтверждено", "ok" if find_by_name(vtags if isinstance(vtags, list) else [], MP_TAG) else "FAIL", vtags)
    mp.step("3 DELETE tags/{id}/views/{viewId} — снять", "DELETE", f"/public/api/tags/{tag_id}/views/{view_id}")
    mp.step("3 GET tags/{id}/elements после снятия", "GET", f"/public/api/tags/{tag_id}/elements")

    # 4. Теги VDP внутри маркетплейса — только на чтение?
    with test.connect() as c:
        vql("4 VQL: назначить тег VDP представлению", c,
            f"ALTER TAG {VDP_TAG} ADD_TO ( VIEWS ( {TEST_DB}.{TEST_VIEW} ) COLUMNS () ) REMOVE_FROM ( VIEWS () COLUMNS () )")
    st, vdp_tags, _ = mp.step("4 GET tags/vdp — теги VDP, доступные для импорта", "GET", "/public/api/tags/vdp")
    record("4 тег VDP виден без синхронизации каталога?", "ok" if find_by_name(vdp_tags, VDP_TAG) else "FAIL",
           [t.get("name") for t in vdp_tags] if isinstance(vdp_tags, list) else vdp_tags)
    st, before, _ = mp.call("GET", "/public/api/tags")
    imported_before = [t["name"] for t in before if t.get("vdpTag")]
    record("4 импортированные теги VDP в маркетплейсе до synchronize", "ok", imported_before)
    mp.step("4 POST tags/vdp/synchronize — список из одного тега", "POST", "/public/api/tags/vdp/synchronize",
            body={"vdpTags": [VDP_TAG]})
    st, tags, _ = mp.step("4 GET tags после импорта", "GET", "/public/api/tags")
    imported_after = [t["name"] for t in tags if t.get("vdpTag")]
    record("4 ловушка: synchronize заменяет ВЕСЬ набор импортированных тегов списком из тела?",
           "ok", {"до": imported_before, "после": imported_after,
                  "пропали": sorted(set(imported_before) - set(imported_after))})
    vtag = find_by_name(tags, VDP_TAG)
    vtag_id = vtag["id"] if vtag else None
    record("4 импортированный тег: vdpTag=true?", "ok" if vtag and vtag.get("vdpTag") else "FAIL", vtag)
    mp.step("4 PUT tags на импортированный тег — ожидаем отказ", "PUT", "/public/api/tags",
            body={"id": vtag_id, "name": VDP_TAG, "description": "edited in marketplace", "descriptionType": "TEXT"},
            expect_error=True)
    mp.step("4 POST tags/{vdpTagId}/views — назначить через маркетплейс, ожидаем отказ", "POST",
            f"/public/api/tags/{vtag_id}/views", body=[view_id], expect_error=True)
    st, vtags, _ = mp.step("4 GET views/{viewId}/tags — назначение из VQL видно после импорта?", "GET",
                           f"/public/api/views/{view_id}/tags")
    record("4 назначение VDP-тега видно в маркетплейсе", "ok" if find_by_name(vtags if isinstance(vtags, list) else [], VDP_TAG) else "note", vtags)
    all_vdp = [t["name"] for t in vdp_tags] if isinstance(vdp_tags, list) else [VDP_TAG]
    mp.step("4 POST tags/vdp/synchronize с полным списком тегов VDP — восстановить чужие импорты", "POST",
            "/public/api/tags/vdp/synchronize", body={"vdpTags": all_vdp})
    st, tags, _ = mp.call("GET", "/public/api/tags")
    record("4 чужие импорты восстановлены?", "ok" if set(imported_before) <= {t["name"] for t in tags} else "FAIL",
           [t["name"] for t in tags if t.get("vdpTag")])
    st, tags, _ = mp.step("4 GET tags после повторной синхронизации", "GET", "/public/api/tags")
    record("4 дубликата нет?", "ok" if sum(1 for t in tags if t.get("name") == VDP_TAG) == 1 else "FAIL",
           [t for t in tags if t.get("name") == VDP_TAG])
    mp.step("4 DELETE tags/{vdpTagId} — удалить импортированный тег: ожидаем отказ", "DELETE",
            f"/public/api/tags/{vtag_id}", expect_error=True)
    st, tags, _ = mp.step("4 GET tags после DELETE импортированного", "GET", "/public/api/tags")
    record("4 импортированный тег после DELETE", "ok", find_by_name(tags, VDP_TAG) or "отсутствует")
    with test.connect() as c:
        vql("4 VQL: тег VDP на месте после DELETE в маркетплейсе?", c,
            f"SELECT * FROM GET_VIEW_TAGS() WHERE input_database_name = '{TEST_DB}' AND input_view_name = '{TEST_VIEW}'")

    # 5. Категории
    cat_body = {"name": MP_CAT, "description": "Category created by T11 spike", "descriptionType": "TEXT"}
    mp.step("5 POST categories — создание", "POST", "/public/api/category-management/categories", body=cat_body)
    mp.step("5 POST categories — тот же name повторно, ожидаем ошибку", "POST",
            "/public/api/category-management/categories", body=cat_body, expect_error=True)
    st, cats, _ = mp.step("5 GET categories — найти id", "GET", "/public/api/category-management/categories")
    cat = find_by_name(cats, MP_CAT)
    cat_id = cat["id"] if cat else None
    record("5 категория найдена", "ok" if cat_id else "FAIL", cat)
    mp.step("5 POST categories — вложенная (parentId)", "POST", "/public/api/category-management/categories",
            body={**cat_body, "name": MP_CAT_CHILD, "parentId": cat_id})
    st, cats, _ = mp.step("5 GET categories — id потомка", "GET", "/public/api/category-management/categories")
    child = find_by_name(cats, MP_CAT_CHILD)
    child_id = child["id"] if child else None
    mp.step("5 GET categories/tree", "GET", "/public/api/category-management/categories/tree")
    mp.step("5 PUT categories/{id} — обновление без parentId", "PUT",
            f"/public/api/category-management/categories/{cat_id}",
            body={"name": MP_CAT, "description": "updated by T11 spike", "descriptionType": "TEXT"})
    mp.step("5 GET categories/{id}", "GET", f"/public/api/category-management/categories/{cat_id}")
    mp.step("5 POST categories/{id}/views — назначить представлению", "POST",
            f"/public/api/category-management/categories/{cat_id}/views", body=[view_id])
    mp.step("5 POST categories/{id}/views — повторно", "POST",
            f"/public/api/category-management/categories/{cat_id}/views", body=[view_id])
    st, vcats, _ = mp.step("5 GET views/{viewId}/categories", "GET",
                           f"/public/api/category-management/views/{view_id}/categories")
    record("5 назначение подтверждено", "ok" if find_by_name(vcats if isinstance(vcats, list) else [], MP_CAT) else "FAIL", vcats)
    mp.step("5 DELETE categories/{id}/views?elementIds= — снять", "DELETE",
            f"/public/api/category-management/categories/{cat_id}/views", params={"elementIds": view_id})
    mp.step("5 DELETE categories/{parent} с потомком — отказ или каскад?", "DELETE",
            f"/public/api/category-management/categories/{cat_id}")
    st, cats, _ = mp.step("5 GET categories после попытки удалить родителя", "GET", "/public/api/category-management/categories")
    record("5 родитель/потомок после DELETE", "ok",
           {"parent": bool(find_by_name(cats, MP_CAT)), "child": bool(find_by_name(cats, MP_CAT_CHILD))})
    # категорию для external element держим живой: пересоздадим, если удалилась каскадом
    if not find_by_name(cats, MP_CAT):
        mp.step("5 POST categories — пересоздать для шага 6", "POST", "/public/api/category-management/categories", body=cat_body)
        st, cats, _ = mp.call("GET", "/public/api/category-management/categories")
        cat_id = (find_by_name(cats, MP_CAT) or {}).get("id")
        child_id = None

    # 6. External elements
    st, created_type, _ = mp.step("6 POST external-elements-types — тип элемента", "POST", "/public/api/external-elements-types",
                                  body={"name": EXT_TYPE, "description": "T11 spike type", "visualName": "T11 test type",
                                        "iconKey": "fas fa-flask", "iconColorCode": "#1F3A5F", "reversedIconColorCode": "#fff"})
    mp.step("6 POST external-elements-types — дубликат, ожидаем ошибку", "POST", "/public/api/external-elements-types",
            body={"name": EXT_TYPE, "description": "dup", "visualName": "T11 test type", "iconKey": "fas fa-flask",
                  "iconColorCode": "#1F3A5F", "reversedIconColorCode": "#fff"}, expect_error=True)
    type_id = (created_type or {}).get("externalElementTypeId") if isinstance(created_type, dict) else None
    st, created_prov, _ = mp.step("6 POST external-providers-types — тип провайдера (multipart с иконкой)", "POST",
                                  "/public/api/external-providers-types",
                                  multipart={"request": (None, json.dumps({"name": EXT_PROVIDER, "visualName": "T11 test provider"}).encode(), "application/json"),
                                             "icon": ("t11.svg", ICON_SVG, "image/svg+xml")})
    provider_id = (created_prov or {}).get("externalProviderTypeId") if isinstance(created_prov, dict) else None
    mp.step("6 POST external-providers-types — дубликат, ожидаем ошибку", "POST", "/public/api/external-providers-types",
            multipart={"request": (None, json.dumps({"name": EXT_PROVIDER, "visualName": "T11 test provider"}).encode(), "application/json"),
                       "icon": ("t11.svg", ICON_SVG, "image/svg+xml")}, expect_error=True)
    server_body = {"type": "CUSTOM", "name": EXT_SERVER, "description": "T11 spike custom server",
                   "externalProviderTypeId": provider_id, "databaseName": TEST_DB, "viewName": EXT_IFACE}
    st, created_srv, _ = mp.step("6 POST external-tool-servers — CUSTOM (interface view ещё не существует)", "POST",
                                 "/public/api/external-tool-servers", body=server_body)
    ext_srv_id = (created_srv or {}).get("id") if isinstance(created_srv, dict) else None
    if ext_srv_id is None:
        st, srvs, _ = mp.call("GET", "/public/api/external-tool-servers")
        ext_srv_id = (find_by_name(srvs, EXT_SERVER) or {}).get("id")
        record("6 id сервера из списка (POST не вернул тело)", "ok" if ext_srv_id else "FAIL", ext_srv_id)
    mp.step("6 POST external-tool-servers — то же имя повторно", "POST", "/public/api/external-tool-servers",
            body=server_body, expect_error=True)
    st, srvs, _ = mp.step("6 GET external-tool-servers — список (есть ли databaseName/viewName?)", "GET",
                          "/public/api/external-tool-servers")
    st, vql_meta, hdrs = mp.step("6 GET external-tool-servers/{id}/vql-metadata — VQL контракта", "GET",
                                 f"/public/api/external-tool-servers/{ext_srv_id}/vql-metadata")
    record("6 vql-metadata content-type", "ok", hdrs.get("Content-Type"))
    vql_text = vql_meta if isinstance(vql_meta, str) else json.dumps(vql_meta)
    with test.connect() as c:
        for stmt in [s.strip() for s in vql_text.split(";") if s.strip()]:
            if stmt.upper().startswith("CONNECT DATABASE"):
                continue  # соединение уже в тестовой базе (отчёт T2, 3.4)
            vql(f"6 VQL из vql-metadata: {stmt.split('(')[0].strip()[:60]}", c, stmt)
        vql("6 VQL: плоское представление элемента с одной ассоциацией", c, EXT_FLAT_VQL)
        vql("6 VQL: NEST ассоциаций в массив", c, EXT_NEST_VQL)
        vql("6 VQL: ALTER INTERFACE VIEW SET IMPLEMENTATION", c,
            f"ALTER INTERFACE VIEW {EXT_IFACE} SET IMPLEMENTATION t11_ext_elements")
        vql("6 VQL: SELECT из interface view", c, f"SELECT id, name, external_element_type FROM {EXT_IFACE}")
    st, sync, _ = mp.step("6 POST external-tool-servers/synchronize — первая синхронизация", "POST",
                          "/public/api/external-tool-servers/synchronize", body={"externalToolServerIds": [ext_srv_id]})
    search_body = {"text": EXT_ELEMENT_NAME, "externalElementTypeIds": [], "withEndorsements": False, "withWarnings": False,
                   "withDeprecations": False, "categoryIds": [], "tagIds": [], "externalToolServerIds": [],
                   "offset": 0, "limit": 20, "whereToSearchList": ["ELEMENT_NAME"], "searchType": "EXACT_MATCH"}
    st, found, _ = mp.step("6 POST search/external-elements/metadata — найти элемент по имени", "POST",
                           "/public/api/search/external-elements/metadata", body=search_body)
    elems = (found or {}).get("elements") if isinstance(found, dict) else None
    elem = elems[0] if elems else None
    elem_id = elem.get("id") if elem else None
    record("6 элемент найден, тип и originalExternalElementId", "ok" if elem else "FAIL",
           {k: elem.get(k) for k in ("id", "name", "typeName", "originalExternalElementId", "externalToolServerName")} if elem else found)
    mp.step("6 GET external-elements/{id}/details", "GET", f"/public/api/external-elements/{elem_id}/details")
    mp.step("6 POST tags/{tagId}/external-elements — назначить тег", "POST",
            f"/public/api/tags/{tag_id}/external-elements", body=[elem_id])
    mp.step("6 GET tags/{tagId}/external-elements", "GET", f"/public/api/tags/{tag_id}/external-elements")
    mp.step("6 POST categories/{catId}/external-elements — назначить категорию", "POST",
            f"/public/api/category-management/categories/{cat_id}/external-elements", body=[elem_id])
    mp.step("6 GET categories/{catId}/external-elements", "GET",
            f"/public/api/category-management/categories/{cat_id}/external-elements")
    mp.step("6 PUT external-elements/{id}/description — правка на стороне маркетплейса", "PUT",
            f"/public/api/external-elements/{elem_id}/description",
            body={"description": "edited in marketplace by T11 spike", "descriptionType": "TEXT"})
    mp.step("6 POST external-tool-servers/synchronize — повторно без изменений", "POST",
            "/public/api/external-tool-servers/synchronize", body={"externalToolServerIds": [ext_srv_id]})
    st, found, _ = mp.step("6 поиск после повторной синхронизации — тег и категория на месте?", "POST",
                           "/public/api/search/external-elements/metadata", body=search_body)
    elem2 = ((found or {}).get("elements") or [None])[0] if isinstance(found, dict) else None
    record("6 после повторной синхронизации", "ok" if elem2 else "FAIL",
           {k: elem2.get(k) for k in ("id", "tags", "categories", "description")} if elem2 else found)
    mp.step("6 DELETE external-tool-servers/{id}", "DELETE", f"/public/api/external-tool-servers/{ext_srv_id}")
    st, found, _ = mp.step("6 поиск после удаления сервера — элемент исчез?", "POST",
                           "/public/api/search/external-elements/metadata", body=search_body)
    record("6 элементы после удаления сервера", "ok", (found or {}).get("elements") if isinstance(found, dict) else found)
    mp.step("6 DELETE external-tool-servers/{id} повторно — ожидаем ошибку", "DELETE",
            f"/public/api/external-tool-servers/{ext_srv_id}", expect_error=True)
    mp.step("6 DELETE external-providers-types/{id}", "DELETE", f"/public/api/external-providers-types/{provider_id}")
    mp.step("6 DELETE external-elements-types/{id}", "DELETE", f"/public/api/external-elements-types/{type_id}")
    mp.step("6 DELETE external-elements-types/{id} повторно — ожидаем ошибку", "DELETE",
            f"/public/api/external-elements-types/{type_id}", expect_error=True)

    # 7. Уборка
    mp.step("7 DELETE tags/{id}", "DELETE", f"/public/api/tags/{tag_id}")
    mp.step("7 DELETE tags/{id} повторно — ожидаем ошибку", "DELETE", f"/public/api/tags/{tag_id}", expect_error=True)
    if child_id:
        mp.step("7 DELETE categories/{child}", "DELETE", f"/public/api/category-management/categories/{child_id}")
    if cat_id:
        mp.step("7 DELETE categories/{parent}", "DELETE", f"/public/api/category-management/categories/{cat_id}")
        mp.step("7 DELETE categories/{parent} повторно — идемпотентно, 200", "DELETE",
                f"/public/api/category-management/categories/{cat_id}")
    test.dispose()
    admin = make_engine(profile, profile.get("database", "admin"))
    with admin.connect() as c:
        vql("7 DROP TAG с назначением на представление — ожидаем отказ (Some elements depend on)", c,
            f"DROP TAG IF EXISTS {VDP_TAG}", expect_error=True)
        vql("7 DROP DATABASE IF EXISTS", c, f"DROP DATABASE IF EXISTS {TEST_DB}")
        vql("7 DROP TAG IF EXISTS после DROP DATABASE — зависимость ушла вместе с базой", c,
            f"DROP TAG IF EXISTS {VDP_TAG}")
    admin.dispose()
    st, vdp_now, _ = mp.step("7 GET tags/vdp/changes — что маркетплейс считает расхождением", "GET",
                             "/public/api/tags/vdp/changes")
    remaining = [t["name"] for t in mp.call("GET", "/public/api/tags/vdp")[1]]
    mp.step("7 POST tags/vdp/synchronize с актуальным списком VDP — убирает импортированную копию", "POST",
            "/public/api/tags/vdp/synchronize", body={"vdpTags": remaining})
    mp.step("7 element-management/all/synchronize — убрать базу из маркетплейса", "POST",
            "/public/api/element-management/all/synchronize", body={"proceedWithConflicts": "SERVER"})
    st, dbs, _ = mp.step("7 local/databases после уборки", "GET", "/public/api/database-management/local/databases")
    record("7 тестовой базы в маркетплейсе нет?", "ok" if not find_by_name(dbs, TEST_DB, "databaseName") else "FAIL",
           [d.get("databaseName") for d in dbs] if isinstance(dbs, list) else dbs)
    st, tags, _ = mp.call("GET", "/public/api/tags")
    st, cats, _ = mp.call("GET", "/public/api/category-management/categories")
    record("7 следов t11_ в тегах/категориях нет?",
           "ok" if not any(t.get("name", "").startswith("t11_") for t in (tags or []) + (cats or [])) else "FAIL", "")

    # Итог
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    bad = [r for r in results if r["status"] in ("FAIL", "UNEXPECTED_OK")]
    print(f"\nшагов: {len(results)}, расхождений с ожиданием: {len(bad)}", file=sys.stderr)
    for r in bad:
        print(f"  {r['status']}: {r['step']} — {r['detail'][:200]}", file=sys.stderr)
    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
