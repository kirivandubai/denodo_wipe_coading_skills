"""Write the fixture files of the verification chain: synthetic rows under the TPC-DS names.

The chain's fixtures read five delimited files through a DF data source; any server can reach
them over HTTP from the repository, or from a folder they were copied into (see README.md here).
They are laid out like the TPC-DS files — the header quoted and upper case, text columns padded to
their CHAR width, an empty field for NULL — so one set of wrappers reads either.

- income_band and household_demographics follow the TPC-DS definitions: twenty bands of 10,000,
  and 7,200 households, every combination of band, buy potential, dependants and vehicles once.
  The chain's checks and the testing templates count on both.
- reason, store_returns and web_returns are invented under the TPC-DS column names. No check
  reads their exact contents; the returns carry NULL date and reason keys, as the templates over
  them expect.

Deterministic (a fixed seed, no clock): running it again rewrites the same bytes, and a unit test
holds the committed files to that. Standard library only:

    python3 verification/data/generate.py
"""

from __future__ import annotations

import random
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


def _maybe(rng: random.Random, value, share: float = 0.03):
    return None if rng.random() < share else value


def _money(rng: random.Random, low: float, high: float) -> str:
    return f"{rng.uniform(low, high):.2f}"


def store_returns(rng: random.Random, count: int = 2000):
    for ticket in range(1, count + 1):
        amount = float(_money(rng, 1, 2000))
        tax = round(amount * 0.08, 2)
        yield (_maybe(rng, rng.randint(FIRST_DATE_KEY, LAST_DATE_KEY)), rng.randint(28800, 75600),
               rng.randint(1, 18000), _maybe(rng, rng.randint(1, 100000)), rng.randint(1, 1920800),
               rng.randint(1, 7200), rng.randint(1, 50000), rng.randint(1, 12),
               _maybe(rng, rng.randint(1, len(REASONS))), ticket, rng.randint(1, 100),
               f"{amount:.2f}", f"{tax:.2f}", f"{amount + tax:.2f}", _money(rng, 0.5, 100),
               _money(rng, 0, 1000), _money(rng, 0, amount), _money(rng, 0, 500),
               _money(rng, 0, 500), _money(rng, 0, 1500))


def web_returns(rng: random.Random, count: int = 1000):
    for order in range(1, count + 1):
        customer, cdemo, hdemo, addr = (rng.randint(1, 100000), rng.randint(1, 1920800),
                                        rng.randint(1, 7200), rng.randint(1, 50000))
        amount = float(_money(rng, 1, 3000))
        tax = round(amount * 0.08, 2)
        yield (_maybe(rng, rng.randint(FIRST_DATE_KEY, LAST_DATE_KEY)), rng.randint(0, 86399),
               rng.randint(1, 18000), customer, cdemo, hdemo, addr, customer, cdemo, hdemo, addr,
               rng.randint(1, 60), _maybe(rng, rng.randint(1, len(REASONS))), order,
               rng.randint(1, 100), f"{amount:.2f}", f"{tax:.2f}", f"{amount + tax:.2f}",
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


FILES = ("income_band", "household_demographics", "reason", "store_returns", "web_returns")


def main(folder: Path = HERE) -> None:
    rng = random.Random(40)
    _write(folder, "income_band", ["IB_INCOME_BAND_SK", "IB_LOWER_BOUND", "IB_UPPER_BOUND"], income_band())
    _write(folder, "household_demographics", ["HD_DEMO_SK", "HD_INCOME_BAND_SK", "HD_BUY_POTENTIAL",
                                              "HD_DEP_COUNT", "HD_VEHICLE_COUNT"], household_demographics())
    _write(folder, "reason", ["R_REASON_SK", "R_REASON_ID", "R_REASON_DESC"], reason())
    _write(folder, "store_returns", STORE_RETURNS, store_returns(rng))
    _write(folder, "web_returns", WEB_RETURNS, web_returns(rng))


if __name__ == "__main__":
    main()
