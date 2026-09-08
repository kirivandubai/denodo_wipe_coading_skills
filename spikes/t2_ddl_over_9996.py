# /// script
# requires-python = ">=3.11"
# dependencies = ["denodo-sqlalchemy>=2.0.5", "psycopg2-binary>=2.9.6"]
# ///
"""Спайк T2: проходит ли DDL через канал 9996 (denodo+psycopg2).

Запуск:  uv run spikes/t2_ddl_over_9996.py --env dev [--csv /путь/на/сервере.csv]
Профиль берётся из ~/.denodo/profiles.toml (или $DENODO_PROFILES); креденшелы в
аргументах не передаются. Всё создаётся в отдельной базе и удаляется в конце.
CSV должен лежать на сервере Denodo (не на машине, где запущен скрипт) и иметь
заголовок cust_id,first_name,last_name,email,country,city,created_dt,segment_cd.
Результаты прогона — docs/superpowers/specs/2026-09-08-spike-t2-ddl-over-9996.md.

Что проверяется, по шагам:
  1. SELECT 1 — канал жив.
  2. DDL внутри транзакции psycopg2 и в режиме AUTOCOMMIT — какой режим нужен.
  3. Полная цепочка v1: DATABASE → FOLDER → TAG → DATASOURCE DF → WRAPPER DF →
     TABLE (базовое представление) → VIEW → INTERFACE VIEW → ASSOCIATION, с SELECT из
     базового представления.
  4. Идемпотентность: повторный CREATE OR REPLACE каждого типа; ошибка обычного CREATE
     поверх существующего объекта (текст ошибки — материал для references/errors.md).
  5. DROP ... IF EXISTS для каждого типа — дважды, второй раз по уже удалённому объекту.
  6. Ловушки клиента: `:text` в декларациях колонок против sqlalchemy.text(), `%` в VQL
     против psycopg2, несколько выражений через `;` в одном execute.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from pathlib import Path

import sqlalchemy as sa

TEST_DB = "denodo_skills_test"
CSV_ON_SERVER = "/data/demo-data/crm/customers.csv"  # дефолт для стенда автора, см. --csv

results: list[dict] = []


def step(name: str, conn, vql: str, *, expect_error: bool = False, via_text: bool = False):
    """Выполнить одно выражение и записать исход. Возвращает строки или None."""
    try:
        cur = conn.execute(sa.text(vql)) if via_text else conn.exec_driver_sql(vql)
        rows = cur.fetchall() if cur.returns_rows else None
        status = "UNEXPECTED_OK" if expect_error else "ok"
        results.append({"step": name, "status": status, "detail": _short(rows)})
        return rows
    except Exception as exc:  # noqa: BLE001 — спайк, нам нужен текст любой ошибки
        msg = " ".join(str(exc).split())
        status = "expected_error" if expect_error else "FAIL"
        results.append({"step": name, "status": status, "detail": msg[:300]})
        return None


def _short(rows):
    if rows is None:
        return ""
    return json.dumps([list(map(str, r)) for r in rows[:3]], ensure_ascii=False)


def load_profile(env: str) -> dict:
    path = Path(os.environ.get("DENODO_PROFILES", "~/.denodo/profiles.toml")).expanduser()
    with path.open("rb") as fh:
        profiles = tomllib.load(fh)
    if env not in profiles:
        sys.exit(f"профиль {env!r} не найден в {path}")
    return profiles[env]


def make_engine(p: dict, database: str, autocommit: bool) -> sa.Engine:
    url = sa.URL.create(
        "denodo+psycopg2",
        username=p["user"],
        password=p["password"],
        host=p["host"],
        port=int(p.get("port", 9996)),
        database=database,
    )
    engine = sa.create_engine(url)
    if autocommit:
        # Диалект Denodo не реализует set_isolation_level, поэтому
        # isolation_level="AUTOCOMMIT" в create_engine падает NotImplementedError.
        # Автокоммит включается на DBAPI-соединении psycopg2 при каждом connect.
        @sa.event.listens_for(engine, "connect")
        def _autocommit(dbapi_conn, _record):
            dbapi_conn.autocommit = True
    return engine


# --- VQL-шаблоны цепочки -------------------------------------------------------------

VQL = {
    "folder": "CREATE OR REPLACE FOLDER '/spike'",
    "tag": "CREATE OR REPLACE TAG spike_tag DESCRIPTION = 'tag created by T2 spike'",
    "datasource": """CREATE OR REPLACE DATASOURCE DF spike_ds
    FOLDER = '/spike'
    ROUTE LOCAL 'LocalConnection' '{csv}' FILENAMEPATTERN = ''
    CHARSET = 'UTF-8'
    COLUMNDELIMITER = ','
    ENDOFLINEDELIMITER = '\\n'
    HEADER = TRUE""",
    "wrapper": """CREATE OR REPLACE WRAPPER DF spike_wr
    FOLDER = '/spike'
    DATASOURCENAME = spike_ds
    OUTPUTSCHEMA (
        cust_id = 'cust_id',
        first_name = 'first_name',
        last_name = 'last_name',
        email = 'email',
        country = 'country',
        city = 'city',
        created_dt = 'created_dt',
        segment_cd = 'segment_cd'
    )""",
    # Ловушка стенда: wrapper DF, перечисляющий не все колонки CSV, создаётся без ошибки,
    # но SELECT из базового представления возвращает ноль строк.
    "wrapper_partial": """CREATE OR REPLACE WRAPPER DF spike_wr_partial
    FOLDER = '/spike'
    DATASOURCENAME = spike_ds
    OUTPUTSCHEMA (
        cust_id = 'cust_id',
        country = 'country',
        city = 'city'
    )""",
    "table_partial": """CREATE OR REPLACE TABLE spike_bv_partial I18N us_pst (
        cust_id:text,
        country:text,
        city:text
    )
    FOLDER = '/spike'
    CACHE OFF
    TIMETOLIVEINCACHE DEFAULT
    ADD SEARCHMETHOD spike_wr_partial (
        OUTPUTLIST ( cust_id, country, city )
        WRAPPER (df spike_wr_partial)
    )""",
    "table": """CREATE OR REPLACE TABLE spike_bv I18N us_pst (
        cust_id:text,
        first_name:text,
        last_name:text,
        email:text,
        country:text,
        city:text,
        created_dt:text,
        segment_cd:text
    )
    FOLDER = '/spike'
    CACHE OFF
    TIMETOLIVEINCACHE DEFAULT
    ADD SEARCHMETHOD spike_wr (
        OUTPUTLIST ( cust_id, first_name, last_name, email, country, city, created_dt, segment_cd )
        WRAPPER (df spike_wr)
    )""",
    "view": """CREATE OR REPLACE VIEW spike_dv FOLDER = '/spike'
    DESCRIPTION = 'derived view created by T2 spike'
    AS SELECT country, COUNT(*) AS customers FROM spike_bv GROUP BY country""",
    "interface": """CREATE OR REPLACE INTERFACE VIEW spike_iv (
        country:text,
        customers:long
    )
    SET IMPLEMENTATION spike_dv
    FOLDER = '/spike'""",
    "association": """CREATE OR REPLACE ASSOCIATION spike_assoc
    FOLDER = '/spike'
    ENDPOINT country_stats spike_dv PRINCIPAL (0,1)
    ENDPOINT customers spike_bv (0,*)
    ADD MAPPING country = country""",
}

DROP = {
    "association": "DROP ASSOCIATION IF EXISTS spike_assoc",
    "interface": "DROP INTERFACE VIEW IF EXISTS spike_iv",
    "view": "DROP VIEW IF EXISTS spike_dv",
    "table": "DROP TABLE IF EXISTS spike_bv",
    "table_partial": "DROP TABLE IF EXISTS spike_bv_partial",
    "wrapper": "DROP WRAPPER DF IF EXISTS spike_wr",
    "wrapper_partial": "DROP WRAPPER DF IF EXISTS spike_wr_partial",
    "datasource": "DROP DATASOURCE DF IF EXISTS spike_ds",
    "tag": "DROP TAG IF EXISTS spike_tag",
    "folder_a": "DROP FOLDER IF EXISTS '/spike/a'",
    "folder_b": "DROP FOLDER IF EXISTS '/spike/b'",
    "folder": "DROP FOLDER IF EXISTS '/spike'",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True)
    ap.add_argument("--csv", default=CSV_ON_SERVER, help="путь к CSV на сервере Denodo")
    args = ap.parse_args()
    VQL["datasource"] = VQL["datasource"].format(csv=args.csv)
    profile = load_profile(args.env)
    if profile.get("production"):
        sys.exit("профиль помечен production=true — спайк на нём не запускается")

    # 1. Канал жив?
    admin_tx = make_engine(profile, profile.get("database", "admin"), autocommit=False)
    with admin_tx.connect() as c:
        step("1 SELECT 1 (транзакционный режим)", c, "SELECT 1")
        step("1 версия сервера (первая строка DESC VQL DATABASE)", c,
             "DESC VQL DATABASE admin")
        step("0 чистый старт: DROP DATABASE IF EXISTS тестовой базы", c,
             f"DROP DATABASE IF EXISTS {TEST_DB}")
        step("0 чистый старт: DROP DATABASE IF EXISTS _tx", c,
             f"DROP DATABASE IF EXISTS {TEST_DB}_tx")
        c.commit()
        # 2а. DDL внутри неявной транзакции psycopg2 — коммит делает SQLAlchemy при close
        step("2a CREATE DATABASE в транзакции (без autocommit)", c,
             f"CREATE DATABASE {TEST_DB}_tx 'T2 spike, transactional mode'")
        c.commit()
    with admin_tx.connect() as c:
        rows = step("2a база видна из нового соединения после commit?", c, "LIST DATABASES")
        if rows is not None:
            results[-1]["detail"] = "есть" if any(r[0] == f"{TEST_DB}_tx" for r in rows) else "НЕТ"
        step("2a DROP DATABASE _tx", c, f"DROP DATABASE IF EXISTS {TEST_DB}_tx")
        c.commit()
    admin_tx.dispose()

    admin = make_engine(profile, profile.get("database", "admin"), autocommit=True)
    with admin.connect() as c:
        # 2б. Тот же DDL в AUTOCOMMIT — основной режим всего дальнейшего
        step("2b CREATE DATABASE (autocommit)", c, f"CREATE DATABASE {TEST_DB} 'T2 spike'")
        step("4 CREATE DATABASE поверх существующей — ожидаем ошибку", c,
             f"CREATE DATABASE {TEST_DB} 'T2 spike'", expect_error=True)
        step("4 CREATE OR REPLACE DATABASE повторно", c,
             f"CREATE OR REPLACE DATABASE {TEST_DB} 'T2 spike, replaced'")
        # CONNECT DATABASE через 9996 — переключается ли сессия?
        step("3 CONNECT DATABASE через 9996", c, f"CONNECT DATABASE {TEST_DB}")
        step("3 FOLDER после CONNECT (в какой базе окажется?)", c, VQL["folder"])
        step("3 где создалась папка (GET_ELEMENTS по тестовой базе)", c,
             f"SELECT database_name, name, type FROM GET_ELEMENTS() WHERE input_database_name = '{TEST_DB}' AND type = 'folder'")
        step("3 DROP DATABASE из соединения после CONNECT — ожидаем ошибку", c,
             f"DROP DATABASE {TEST_DB}", expect_error=True)

    # 3. Полная цепочка — отдельным подключением прямо в тестовую базу
    test = make_engine(profile, TEST_DB, autocommit=True)
    with test.connect() as c:
        for key in ("folder", "tag", "datasource", "wrapper", "table", "view", "interface", "association"):
            step(f"3 CREATE OR REPLACE {key}", c, VQL[key])
        step("3 SELECT из базового представления", c, "SELECT COUNT(*) AS n FROM spike_bv")
        step("3 ловушка: wrapper DF с частью колонок CSV", c, VQL["wrapper_partial"])
        step("3 ловушка: базовое представление над ним", c, VQL["table_partial"])
        step("3 ловушка: SELECT над частичным wrapper — ноль строк, без ошибки", c,
             "SELECT COUNT(*) AS n FROM spike_bv_partial")
        step("3 SELECT из производного представления", c, "SELECT * FROM spike_dv")
        step("3 SELECT из интерфейсного представления", c, "SELECT * FROM spike_iv")
        step("3 тег: ADD_TO без REMOVE_FROM — ожидаем синтаксическую ошибку", c,
             f"ALTER TAG spike_tag ADD_TO ( VIEWS ( {TEST_DB}.spike_dv ) COLUMNS () )",
             expect_error=True)
        step("3 тег: ADD_TO без COLUMNS () — ожидаем синтаксическую ошибку", c,
             f"ALTER TAG spike_tag ADD_TO ( VIEWS ( {TEST_DB}.spike_dv ) ) REMOVE_FROM ( VIEWS () COLUMNS () )",
             expect_error=True)
        step("3 тег: ALTER TAG ... ADD_TO (...) REMOVE_FROM (...) — оба блока обязательны", c,
             f"ALTER TAG spike_tag ADD_TO ( VIEWS ( {TEST_DB}.spike_dv ) COLUMNS ( {TEST_DB}.spike_bv.country ) ) "
             f"REMOVE_FROM ( VIEWS () COLUMNS () )")
        step("3 тег: CREATE OR REPLACE TAG ... ADD_TO (...) REMOVE_FROM (...)", c,
             f"CREATE OR REPLACE TAG spike_tag DESCRIPTION = 'tag created by T2 spike' "
             f"ADD_TO ( VIEWS ( {TEST_DB}.spike_dv ) COLUMNS () ) REMOVE_FROM ( VIEWS () COLUMNS () )")
        step("3 тег: ALTER TAG ... REMOVE_FROM — снятие с колонки", c,
             f"ALTER TAG spike_tag ADD_TO ( VIEWS () COLUMNS () ) "
             f"REMOVE_FROM ( VIEWS () COLUMNS ( {TEST_DB}.spike_bv.country ) )")
        step("3 тег: где назначен (GET_VIEW_TAGS)", c,
             f"SELECT * FROM GET_VIEW_TAGS() WHERE input_database_name = '{TEST_DB}' AND input_view_name = 'spike_dv'")
        step("3 тег: повторный CREATE OR REPLACE TAG без ADD_TO — назначения сохраняются?", c, VQL["tag"])
        step("3 тег: назначения после replace", c,
             f"SELECT * FROM GET_VIEW_TAGS() WHERE input_database_name = '{TEST_DB}' AND input_view_name = 'spike_dv'")
        step("3 тег: inline TAGS (...) в CREATE OR REPLACE VIEW", c,
             VQL["view"].replace("AS SELECT", "TAGS (spike_tag)\n    AS SELECT"))

        # 4. Идемпотентность: второй проход CREATE OR REPLACE по уже существующим объектам
        for key in ("folder", "tag", "datasource", "wrapper", "table", "view", "interface", "association"):
            step(f"4 повторный CREATE OR REPLACE {key}", c, VQL[key])
        step("4 SELECT после повторного прохода (цепочка не сломалась?)", c,
             "SELECT COUNT(*) AS n FROM spike_iv")
        # обычный CREATE поверх существующего — текст ошибки
        for key in ("folder", "tag", "datasource", "wrapper", "table", "view"):
            plain = VQL[key].replace("CREATE OR REPLACE", "CREATE", 1)
            step(f"4 CREATE без OR REPLACE поверх {key} — ожидаем ошибку", c, plain, expect_error=True)

        # 6. Ловушки клиента
        step("6 sqlalchemy.text() с `cust_id:text` (двоеточие после слова — не bind)", c,
             VQL["table"], via_text=True)
        step("6 sqlalchemy.text() с `( :text` (двоеточие после пробела) — ожидаем ошибку", c,
             "SELECT CAST( :text , 1) FROM DUAL()", expect_error=True, via_text=True)
        step("6 `%` в VQL через exec_driver_sql — ожидаем ошибку psycopg2", c,
             "SELECT COUNT(*) AS n FROM spike_bv WHERE city LIKE 'New%'", expect_error=True)
        step("6 `%%` (экранировано) через exec_driver_sql", c,
             "SELECT COUNT(*) AS n FROM spike_bv WHERE city LIKE 'New%%'")
        try:
            cur = c.connection.cursor()
            cur.execute("SELECT COUNT(*) AS n FROM spike_bv WHERE city LIKE 'New%'")
            results.append({"step": "6 `%` через сырой курсор psycopg2 без параметров",
                            "status": "ok", "detail": _short(cur.fetchall())})
        except Exception as exc:  # noqa: BLE001
            results.append({"step": "6 `%` через сырой курсор psycopg2 без параметров",
                            "status": "FAIL", "detail": " ".join(str(exc).split())[:300]})
        step("6 два выражения через `;` в одном execute", c,
             "CREATE OR REPLACE FOLDER '/spike/a'; CREATE OR REPLACE FOLDER '/spike/b'")
        step("6 DESC VIEW (машиночитаемо?)", c, "DESC VIEW spike_dv")
        step("6 DESC VQL VIEW", c, "DESC VQL VIEW spike_dv")
        step("6 DESC VQL DATASOURCE DF", c, "DESC VQL DATASOURCE DF spike_ds")
        step("6 ALTER INTERFACE VIEW ... SET IMPLEMENTATION", c,
             "ALTER INTERFACE VIEW spike_iv SET IMPLEMENTATION spike_dv")

        # 5. DROP IF EXISTS — дважды
        for key, vql in DROP.items():
            step(f"5 {vql.split(' IF')[0]} IF EXISTS", c, vql)
        for key, vql in DROP.items():
            step(f"5 повторно по удалённому: {vql.split(' IF')[0]} IF EXISTS", c, vql)
        step("5 DROP TABLE без IF EXISTS по удалённому — ожидаем ошибку", c,
             "DROP TABLE spike_bv", expect_error=True)
    test.dispose()

    # Пул admin-движка держит соединение, где выполнялся CONNECT DATABASE, — из него
    # тестовую базу удалить нельзя. Нужно свежее соединение.
    admin.dispose()
    with admin.connect() as c:
        step("5 DROP DATABASE IF EXISTS (тестовая база, свежее соединение)", c, f"DROP DATABASE IF EXISTS {TEST_DB}")
        step("5 повторно DROP DATABASE IF EXISTS", c, f"DROP DATABASE IF EXISTS {TEST_DB}")
    admin.dispose()

    # Отчёт
    print("| шаг | статус | детали |")
    print("|---|---|---|")
    for r in results:
        detail = r["detail"].replace("|", "\\|")
        print(f"| {r['step']} | {r['status']} | {detail} |")
    bad = [r for r in results if r["status"] in ("FAIL", "UNEXPECTED_OK")]
    print(f"\nвсего шагов: {len(results)}, проблем: {len(bad)}", file=sys.stderr)


if __name__ == "__main__":
    main()
