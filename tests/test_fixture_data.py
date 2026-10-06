"""The fixture files of the verification chain (T40): synthetic rows under the TPC-DS names.

The chain's checks and the testing templates count on the TPC-DS-defined ones — 20 income bands,
7,200 households, every combination once — and the wrappers read the header exactly as written,
quotes included. The committed files are what the generator writes, byte for byte.
"""

from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "verification" / "data"


def _generator():
    spec = importlib.util.spec_from_file_location("fixture_generate", DATA / "generate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows(name: str) -> list[list[str]]:
    with (DATA / f"{name}.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))[1:]


class FixtureDataTest(unittest.TestCase):
    def test_the_committed_files_are_what_the_generator_writes(self):
        generator = _generator()
        with tempfile.TemporaryDirectory() as tmp:
            generator.main(Path(tmp))
            for name in generator.FILES:
                with self.subTest(file=name):
                    self.assertEqual((Path(tmp) / f"{name}.csv").read_bytes(),
                                     (DATA / f"{name}.csv").read_bytes())

    def test_headers_are_quoted_upper_case_as_the_wrappers_map_them(self):
        for name in _generator().FILES:
            header = (DATA / f"{name}.csv").read_text(encoding="utf-8").splitlines()[0]
            with self.subTest(file=name):
                for column in header.split(","):
                    self.assertRegex(column, r'^"[A-Z_]+"$')

    def test_twenty_income_bands_of_ten_thousand(self):
        rows = _rows("income_band")
        self.assertEqual(len(rows), 20)
        self.assertEqual(rows[0], ["1", "0", "10000"])
        self.assertEqual(rows[-1], ["20", "190001", "200000"])

    def test_every_household_combination_once(self):
        rows = _rows("household_demographics")
        self.assertEqual(len(rows), 7200)
        self.assertEqual(len({tuple(row[1:]) for row in rows}), 7200)
        self.assertEqual(Counter(row[2].strip() for row in rows),
                         {value: 1200 for value in ("0-500", "501-1000", "1001-5000", "5001-10000", ">10000",
                                                    "Unknown")})
        self.assertTrue(all(len(row[2]) == 15 for row in rows))

    def test_returns_carry_null_date_and_reason_keys(self):
        for name, date, reason in (("store_returns", 0, 8), ("web_returns", 0, 12)):
            rows = _rows(name)
            with self.subTest(file=name):
                self.assertGreater(sum(1 for row in rows if row[date] == ""), 0)
                self.assertGreater(sum(1 for row in rows if row[reason] == ""), 0)
                self.assertTrue(all(row[reason] == "" or 1 <= int(row[reason]) <= 35 for row in rows))

    def test_thirty_five_reasons(self):
        rows = _rows("reason")
        self.assertEqual([int(row[0]) for row in rows], list(range(1, 36)))
        self.assertTrue(all(len(row[2]) == 100 for row in rows))


if __name__ == "__main__":
    unittest.main()
