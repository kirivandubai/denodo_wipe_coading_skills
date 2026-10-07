"""Write the fixture files of the verification chain: synthetic rows under the TPC-DS names.

The chain reads eight delimited files and one JSON file through DF and JSON data sources; any
server can reach them over HTTP from the repository, or from a folder they were copied into (see
README.md here).
The TPC-DS ones follow the TPC-DS layout — the header quoted and upper case, text columns padded to
their CHAR width, an empty field for NULL — so one set of wrappers reads either.

- income_band and household_demographics follow the TPC-DS definitions: twenty bands of 10,000,
  and 7,200 households, every combination of band, buy potential, dependants and vehicles once.
  The chain's checks and the testing templates count on both.
- reason, store_returns and web_returns are invented under the TPC-DS column names. No check
  reads their exact contents; the returns carry NULL date and reason keys, as the templates over
  them expect.
- store is the TPC-DS store dimension's layout with an invented history: twelve stores as versions
  with validity dates, one closed, one with two versions starting the same day — what the one row
  per key templates of the views skill choose among. Written without random(), so the files above
  keep their bytes.
- date_dim is the TPC-DS calendar's layout for 2014 to 2018, the years the returns' date keys fall in:
  one row per day, keyed by the julian day number as those keys are. The period templates of the
  metrics skill read it.
- customers.csv and orders.json are the files the data source templates of the skills name
  (a CRM export and an order export): invented rows in the shape those templates read, so the
  chain proves the templates read, not only that they parse. orders.json holds 3 orders with
  4 lines, the numbers the JSON reference states.

Deterministic (a fixed seed, no clock): running it again rewrites the same bytes, and a unit test
holds the committed files to that. Only random() is drawn from — the one method whose sequence
Python keeps the same across versions for a seed. Standard library only:

    python3 verification/data/generate.py
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent

BUY_POTENTIAL = ["0-500", "501-1000", "1001-5000", "5001-10000", ">10000", "Unknown"]   # CHAR(15)
VEHICLES = [0, 1, 2, 3, 4, -1]

# Thirty-five invented return reasons, CHAR(100). The first six read like product reviews: the
# AI steps of the chain classify, score and search them.
REASONS = [
    "The screen cracked after two days",
    "Stopped working after a week",
    "Arrived three weeks late and the box was crushed",
    "Runs small, ordered my usual size and it does not fit",
    "Exactly as described, returning a duplicate gift",
    "Colour is nothing like the photo",
    "Ordered the wrong item",
    "Found a better price elsewhere",
    "No longer needed",
    "Item missing parts",
    "Package was opened",
    "Did not match the description",
    "Defective on arrival",
    "Too large",
    "Too heavy to use",
    "Battery does not hold a charge",
    "Wrong colour sent",
    "Duplicate order",
    "Gift that was not wanted",
    "Quality lower than expected",
    "Instructions missing",
    "Incompatible with my device",
    "Late delivery",
    "Damaged in transit",
    "Customer changed mind",
    "Replaced by a newer model",
    "Bought by mistake",
    "Seller sent a used item",
    "Smell from the material",
    "Noisy during use",
    "Stopped charging",
    "Missing accessories",
    "Size chart was wrong",
    "Not as comfortable as expected",
    "Other reason",
]

FIRST_DATE_KEY, LAST_DATE_KEY = 2456740, 2458474     # julian day keys, as TPC-DS date_dim keys


def _text(value: str, width: int) -> str:
    return '"' + value.ljust(width) + '"'


def _field(value) -> str:
    return "" if value is None else str(value)


def _write(folder: Path, name: str, header: list[str], rows) -> None:
    lines = [",".join(f'"{column}"' for column in header)]
    lines += [",".join(_field(value) for value in row) for row in rows]
    (folder / f"{name}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def income_band():
    for band in range(1, 21):
        yield band, 0 if band == 1 else (band - 1) * 10000 + 1, band * 10000


def household_demographics():
    for demo_sk in range(1, 7201):
        yield (demo_sk, demo_sk % 20 + 1, _text(BUY_POTENTIAL[demo_sk // 20 % 6], 15),
               demo_sk // 120 % 10, VEHICLES[demo_sk // 1200 % 6])


def reason():
    for reason_sk, description in enumerate(REASONS, start=1):
        yield reason_sk, _text(f"R{reason_sk:015d}", 16), _text(description, 100)


def _int(rng: random.Random, low: int, high: int) -> int:
    """An integer in [low, high] from random() alone."""
    return low + int(rng.random() * (high - low + 1))


def _maybe(rng: random.Random, value, share: float = 0.03):
    return None if rng.random() < share else value


def _money(rng: random.Random, low: float, high: float) -> str:
    return f"{low + rng.random() * (high - low):.2f}"


def store_returns(rng: random.Random, count: int = 2000):
    for ticket in range(1, count + 1):
        amount = float(_money(rng, 1, 2000))
        tax = round(amount * 0.08, 2)
        yield (_maybe(rng, _int(rng, FIRST_DATE_KEY, LAST_DATE_KEY)), _int(rng, 28800, 75600),
               _int(rng, 1, 18000), _maybe(rng, _int(rng, 1, 100000)), _int(rng, 1, 1920800),
               _int(rng, 1, 7200), _int(rng, 1, 50000), _int(rng, 1, 12),
               _maybe(rng, _int(rng, 1, len(REASONS))), ticket, _int(rng, 1, 100),
               f"{amount:.2f}", f"{tax:.2f}", f"{amount + tax:.2f}", _money(rng, 0.5, 100),
               _money(rng, 0, 1000), _money(rng, 0, amount), _money(rng, 0, 500),
               _money(rng, 0, 500), _money(rng, 0, 1500))


def web_returns(rng: random.Random, count: int = 1000):
    for order in range(1, count + 1):
        customer, cdemo, hdemo, addr = (_int(rng, 1, 100000), _int(rng, 1, 1920800),
                                        _int(rng, 1, 7200), _int(rng, 1, 50000))
        amount = float(_money(rng, 1, 3000))
        tax = round(amount * 0.08, 2)
        yield (_maybe(rng, _int(rng, FIRST_DATE_KEY, LAST_DATE_KEY)), _int(rng, 0, 86399),
               _int(rng, 1, 18000), customer, cdemo, hdemo, addr, customer, cdemo, hdemo, addr,
               _int(rng, 1, 60), _maybe(rng, _int(rng, 1, len(REASONS))), order,
               _int(rng, 1, 100), f"{amount:.2f}", f"{tax:.2f}", f"{amount + tax:.2f}",
               _money(rng, 0.5, 100), _money(rng, 0, 1000), _money(rng, 0, amount),
               _money(rng, 0, 500), _money(rng, 0, 500), _money(rng, 0, 1500))


STORE_RETURNS = ["SR_RETURNED_DATE_SK", "SR_RETURN_TIME_SK", "SR_ITEM_SK", "SR_CUSTOMER_SK", "SR_CDEMO_SK",
                 "SR_HDEMO_SK", "SR_ADDR_SK", "SR_STORE_SK", "SR_REASON_SK", "SR_TICKET_NUMBER",
                 "SR_RETURN_QUANTITY", "SR_RETURN_AMT", "SR_RETURN_TAX", "SR_RETURN_AMT_INC_TAX", "SR_FEE",
                 "SR_RETURN_SHIP_COST", "SR_REFUNDED_CASH", "SR_REVERSED_CHARGE", "SR_STORE_CREDIT",
                 "SR_NET_LOSS"]
WEB_RETURNS = ["WR_RETURNED_DATE_SK", "WR_RETURNED_TIME_SK", "WR_ITEM_SK", "WR_REFUNDED_CUSTOMER_SK",
               "WR_REFUNDED_CDEMO_SK", "WR_REFUNDED_HDEMO_SK", "WR_REFUNDED_ADDR_SK", "WR_RETURNING_CUSTOMER_SK",
               "WR_RETURNING_CDEMO_SK", "WR_RETURNING_HDEMO_SK", "WR_RETURNING_ADDR_SK", "WR_WEB_PAGE_SK",
               "WR_REASON_SK", "WR_ORDER_NUMBER", "WR_RETURN_QUANTITY", "WR_RETURN_AMT", "WR_RETURN_TAX",
               "WR_RETURN_AMT_INC_TAX", "WR_FEE", "WR_RETURN_SHIP_COST", "WR_REFUNDED_CASH",
               "WR_REVERSED_CHARGE", "WR_ACCOUNT_CREDIT", "WR_NET_LOSS"]


STORE = ["S_STORE_SK", "S_STORE_ID", "S_REC_START_DATE", "S_REC_END_DATE", "S_CLOSED_DATE_SK", "S_STORE_NAME",
         "S_NUMBER_EMPLOYEES", "S_FLOOR_SPACE", "S_HOURS", "S_MANAGER", "S_MARKET_ID", "S_GEOGRAPHY_CLASS",
         "S_MARKET_DESC", "S_MARKET_MANAGER", "S_DIVISION_ID", "S_DIVISION_NAME", "S_COMPANY_ID", "S_COMPANY_NAME",
         "S_STREET_NUMBER", "S_STREET_NAME", "S_STREET_TYPE", "S_SUITE_NUMBER", "S_CITY", "S_COUNTY", "S_STATE",
         "S_ZIP", "S_COUNTRY", "S_GMT_OFFSET", "S_TAX_PRECENTAGE"]
# Versions per store id, as (start, end) — TPC-DS keeps the history of a store as rows with validity
# dates, the open one with no end. Store 5 is closed: its last version has an end and a closed date.
# Store 7 has two versions that start on the same day (a correction): the later surrogate key is the
# newer one, and the earlier is closed the day it opened.
STORE_VERSIONS = {
    1: [("2013-03-13", None)],
    2: [("2013-03-13", "2015-03-12"), ("2015-03-13", None)],
    3: [("2013-03-13", "2014-03-12"), ("2014-03-13", "2016-03-12"), ("2016-03-13", None)],
    4: [("2013-03-13", None)],
    5: [("2013-03-13", "2015-03-12"), ("2015-03-13", "2017-06-30")],
    6: [("2013-03-13", None)],
    7: [("2013-03-13", "2016-03-12"), ("2016-03-13", "2016-03-13"), ("2016-03-13", None)],
    8: [("2013-03-13", "2017-03-12"), ("2017-03-13", None)],
    9: [("2013-03-13", None)],
    10: [("2013-03-13", "2014-09-30"), ("2014-10-01", None)],
    11: [("2013-03-13", None)],
    12: [("2013-03-13", "2016-03-12"), ("2016-03-13", None)],
}
STORE_NAMES = ["ought", "able", "pri", "ese", "anti", "cally", "ation", "eing", "bar", "n st"]
STORE_PLACES = [("Midway", "Williamson County", "TN", "31904"), ("Fairview", "Ziebach County", "SD", "35709"),
                ("Oak Grove", "Walker County", "AL", "38370")]


def _store_id(number: int) -> str:
    """A TPC-DS business key: 16 letters, the number in the shape TPC-DS gives it."""
    return "AAAAAAAA" + "".join("ABCDEFGHIJKLMNOP"[int(digit)] for digit in f"{number:04d}") + "AAAA"


def store():
    surrogate = 0
    for number, versions in STORE_VERSIONS.items():
        city, county, state, zip_code = STORE_PLACES[number % 3]
        for version, (start, end) in enumerate(versions):
            surrogate += 1
            closed = 2458300 if number == 5 and end is not None and version == len(versions) - 1 else None
            yield (surrogate, _store_id(number), start, end, closed,
                   _text(STORE_NAMES[(number + version) % 10], 50), 200 + number * 10 + version,
                   5000000 + number * 1000, _text("8AM-10PM", 20), _text(f"Manager {number}-{version + 1}", 40),
                   number % 10 + 1, _text("Unknown", 100), _text(f"Market of store {number}", 100),
                   _text(f"Market manager {number % 4 + 1}", 40), 1, _text("Unknown", 50), 1,
                   _text("Unknown", 50), _text(str(100 + number), 10), _text("Main", 60), _text("Street", 15),
                   _text("Suite 100", 10), _text(city, 60), _text(county, 30), _text(state, 2),
                   _text(zip_code, 10), _text("United States", 20), -5, f"{0.01 + number / 1000:.2f}")


DATE_DIM = ["D_DATE_SK", "D_DATE_ID", "D_DATE", "D_MONTH_SEQ", "D_WEEK_SEQ", "D_QUARTER_SEQ", "D_YEAR", "D_DOW",
            "D_MOY", "D_DOM", "D_QOY", "D_FY_YEAR", "D_FY_QUARTER_SEQ", "D_FY_WEEK_SEQ", "D_DAY_NAME",
            "D_QUARTER_NAME", "D_HOLIDAY", "D_WEEKEND", "D_FOLLOWING_HOLIDAY", "D_FIRST_DOM", "D_LAST_DOM",
            "D_SAME_DAY_LY", "D_SAME_DAY_LQ", "D_CURRENT_DAY", "D_CURRENT_WEEK", "D_CURRENT_MONTH",
            "D_CURRENT_QUARTER", "D_CURRENT_YEAR"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
JULIAN_2000_01_01 = 2451545


def _julian(day: date) -> int:
    return JULIAN_2000_01_01 + (day - date(2000, 1, 1)).days


def date_dim():
    """Every day of the five calendar years the returns' date keys fall in, keyed as TPC-DS keys it:
    the julian day number. The sequences count from January 1900, as TPC-DS counts them."""
    day = date(2014, 1, 1)
    while day <= date(2018, 12, 31):
        month_seq = (day.year - 1900) * 12 + day.month - 1
        quarter = (day.month - 1) // 3 + 1
        first_dom = day.replace(day=1)
        last_dom = (first_dom.replace(year=day.year + day.month // 12, month=day.month % 12 + 1)
                    - timedelta(days=1))
        try:
            same_day_ly = day.replace(year=day.year - 1)
        except ValueError:                      # 29 February: the 28th of the year before
            same_day_ly = day.replace(year=day.year - 1, day=28)
        dow = (day.weekday() + 1) % 7           # TPC-DS: 0 is Sunday
        week_seq = (day - date(1900, 1, 1)).days // 7 + 1
        yield (_julian(day), _text(f"{_julian(day):016d}", 16), day.isoformat(), month_seq, week_seq,
               (day.year - 1900) * 4 + quarter - 1, day.year, dow, day.month, day.day, quarter, day.year,
               (day.year - 1900) * 4 + quarter - 1, week_seq, _text(DAY_NAMES[day.weekday()], 9),
               _text(f"{day.year}Q{quarter}", 6), _text("N", 1), _text("Y" if dow in (0, 6) else "N", 1),
               _text("N", 1), _julian(first_dom), _julian(last_dom), _julian(same_day_ly),
               _julian(day) - 91, _text("N", 1), _text("N", 1), _text("N", 1), _text("N", 1), _text("N", 1))
        day += timedelta(days=1)


FIRST_NAMES = ["Ana", "Ben", "Chloe", "Dev", "Elif", "Farid", "Grace", "Hiro", "Ines", "Jonas"]
LAST_NAMES = ["Silva", "Okafor", "Martin", "Rao", "Yilmaz", "Haddad", "Kim", "Sato", "Costa", "Berg"]
PLACES = [("PT", "Lisbon"), ("NG", "Lagos"), ("FR", "Lyon"), ("IN", "Pune"), ("TR", "Izmir"),
          ("AE", "Dubai"), ("KR", "Busan"), ("JP", "Osaka"), ("BR", "Recife"), ("NO", "Bergen")]


def customers(rng: random.Random, count: int = 40):
    for number in range(1, count + 1):
        first, last = FIRST_NAMES[number % 10], LAST_NAMES[number * 7 % 10]
        country, city = PLACES[number * 3 % 10]
        email = "" if number % 9 == 0 else f"{first.lower()}.{last.lower()}{number}@example.com"
        created = f"20{21 + number % 5}-{1 + number % 12:02d}-{1 + number % 28:02d}"
        yield f"C-{10000 + number}", first, last, email, country, city, created, "ABC"[_int(rng, 0, 2)]


ORDERS = [
    {"order_id": "O-1001", "customer_id": "C-10001", "order_dt": "2026-09-01T10:15:00", "status": "shipped",
     "total_amount": 96.5, "shipping": {"country": "PT", "city": "Lisbon", "zip": "1100-148"},
     "lines": [{"line_no": 1, "sku": "SKU-100", "qty": 2, "price": 18.25},
               {"line_no": 2, "sku": "SKU-200", "qty": 6, "price": 10.0}]},
    {"order_id": "O-1002", "customer_id": "C-10002", "order_dt": "2026-09-02T16:40:00", "status": "open",
     "total_amount": 42.0, "shipping": {"country": "NG", "city": "Lagos", "zip": "100001"},
     "lines": [{"line_no": 1, "sku": "SKU-300", "qty": 1, "price": 42.0}]},
    {"order_id": "O-1003", "customer_id": "C-10003", "order_dt": "2026-09-03T09:05:00", "status": "cancelled",
     "total_amount": 15.0, "shipping": {"country": "FR", "city": "Lyon", "zip": "69001"},
     "lines": [{"line_no": 1, "sku": "SKU-100", "qty": 1, "price": 15.0}]},
]


def _write_orders(folder: Path) -> None:
    (folder / "orders.json").write_text(json.dumps(ORDERS, indent=2) + "\n", encoding="utf-8", newline="\n")


FILES = ("income_band", "household_demographics", "reason", "store_returns", "web_returns", "customers",
         "orders", "store", "date_dim")


def main(folder: Path = HERE) -> None:
    rng = random.Random(40)
    _write(folder, "income_band", ["IB_INCOME_BAND_SK", "IB_LOWER_BOUND", "IB_UPPER_BOUND"], income_band())
    _write(folder, "household_demographics", ["HD_DEMO_SK", "HD_INCOME_BAND_SK", "HD_BUY_POTENTIAL",
                                              "HD_DEP_COUNT", "HD_VEHICLE_COUNT"], household_demographics())
    _write(folder, "reason", ["R_REASON_SK", "R_REASON_ID", "R_REASON_DESC"], reason())
    _write(folder, "store_returns", STORE_RETURNS, store_returns(rng))
    _write(folder, "web_returns", WEB_RETURNS, web_returns(rng))
    _write(folder, "customers", ["cust_id", "first_name", "last_name", "email", "country", "city", "created_dt",
                                 "segment_cd"], customers(rng))
    _write_orders(folder)
    _write(folder, "store", STORE, store())
    _write(folder, "date_dim", DATE_DIM, date_dim())


if __name__ == "__main__":
    main()
