"""denodo_exec's records: canonical JSON, atomic files, JSONL appended and read back."""

import hashlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from denodo_exec import canonical, files
from denodo_exec.errors import CanonicalError, Refused

UTC = timezone.utc


class CanonicalTest(unittest.TestCase):
    def test_keys_are_sorted_by_code_point_and_separators_are_tight(self):
        self.assertEqual(canonical.canonical_json({"b": 1, "a": 2}), '{"a":2,"b":1}')
        self.assertEqual(canonical.canonical_json({"Z": 1, "a": 2, "A": 3}), '{"A":3,"Z":1,"a":2}')

    def test_non_ascii_is_not_escaped_and_nesting_is_canonical_all_the_way_down(self):
        self.assertEqual(canonical.canonical_json({"k": "γειά"}), '{"k":"γειά"}')
        value = {"outer": {"b": [{"d": 1, "c": 2}], "a": None}}
        self.assertEqual(canonical.canonical_json(value), '{"outer":{"a":null,"b":[{"c":2,"d":1}]}}')

    def test_what_has_no_canonical_form_is_refused(self):
        for value in ({"score": 0.5}, {"nested": {"score": 1.0}}, {"list": [1, 2.5]},
                      [float("nan")], {1: "one"}, {"when": datetime(2026, 3, 4, tzinfo=UTC)}):
            with self.subTest(value=value), self.assertRaises(CanonicalError):
                canonical.canonical_json(value)

    def test_decimalising_makes_a_float_carrying_answer_canonical(self):
        value = {"rows": [[612.0, True, 17, None]], "t": ({"a": 1.5},)}
        self.assertEqual(canonical.decimalise_floats(value),
                         {"rows": [["612.0", True, 17, None]], "t": [{"a": "1.5"}]})

    def test_the_digest_is_of_the_canonical_bytes_whatever_the_key_order(self):
        self.assertEqual(canonical.digest_canonical({"a": 1, "b": 2}),
                         canonical.digest_canonical({"b": 2, "a": 1}))
        self.assertEqual(canonical.digest_canonical({}),
                         "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a")

    def test_a_timestamp_is_utc_with_milliseconds_truncated(self):
        moment = datetime(2026, 3, 4, 13, 0, 0, 999_999, tzinfo=timezone(timedelta(hours=3)))
        self.assertEqual(canonical.format_timestamp(moment), "2026-03-04T10:00:00.999Z")
        with self.assertRaises(CanonicalError):
            canonical.format_timestamp(datetime(2026, 3, 4, 10, 0, 0))

    def test_the_canonical_error_is_one_of_the_layer(self):
        from denodo_exec.errors import ExecError
        self.assertTrue(issubclass(CanonicalError, ExecError))


class FilesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_write_is_whole_or_absent(self):
        path = self.tmp / "state.json"
        files.write_json(path, {"a": 1})
        with mock.patch("denodo_exec.files.os.replace", side_effect=OSError("disk full")), \
                self.assertRaises(OSError):
            files.write_json(path, {"a": 2})
        self.assertEqual(files.read_json(path), {"a": 1})
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["state.json"])

    def test_a_float_never_enters_a_file_and_a_digest_takes_its_decimal_spelling(self):
        with self.assertRaises(CanonicalError):
            files.write_json(self.tmp / "x.json", {"score": 0.5})
        self.assertEqual(files.digest({"score": 0.5}), files.digest({"score": "0.5"}))

    def test_jsonl_lines_are_appended_and_read_back(self):
        path = self.tmp / "ledger.jsonl"
        files.append_jsonl(path, {"n": 1})
        files.append_jsonl(path, {"n": 2})
        self.assertEqual(files.read_jsonl(path), [{"n": 1}, {"n": 2}])
        self.assertEqual(path.read_bytes(), b'{"n":1}\n{"n":2}\n')
        self.assertEqual(files.read_jsonl(self.tmp / "none.jsonl"), [])

    def test_a_torn_last_line_is_left_out_and_mended_by_the_next_append(self):
        path = self.tmp / "ledger.jsonl"
        path.write_bytes(b'{"n":1}\n{"n":')
        self.assertEqual(files.read_jsonl(path), [{"n": 1}])
        files.append_jsonl(path, {"n": 2})
        self.assertEqual(path.read_bytes(), b'{"n":1}\n{"n":2}\n')
        path.write_bytes(b'{"n":1}\n{"n":2}')
        files.append_jsonl(path, {"n": 3})
        self.assertEqual(files.read_jsonl(path), [{"n": 1}, {"n": 2}, {"n": 3}])

    def test_a_malformed_line_in_the_middle_is_still_refused(self):
        path = self.tmp / "ledger.jsonl"
        path.write_bytes(b'{"n":1}\nnot json\n{"n":2}\n')
        with self.assertRaisesRegex(Refused, "line 2 is not JSON"):
            files.read_jsonl(path)

    def test_a_ledger_overwritten_with_bytes_refuses_in_a_sentence(self):
        path = self.tmp / "ledger.jsonl"
        path.write_bytes(b"\xff\xfe\x00")
        with self.assertRaisesRegex(Refused, "is not text"):
            files.read_jsonl(path)

    def test_append_jsonl_refuses_a_link(self):
        target = self.tmp / "elsewhere.jsonl"
        target.write_bytes(b"")
        link = self.tmp / "ledger.jsonl"
        link.symlink_to(target)
        with self.assertRaisesRegex(Refused, "is a link"):
            files.append_jsonl(link, {"n": 1})
        self.assertEqual(target.read_bytes(), b"")

    def test_a_missing_or_broken_json_file_is_refused_in_a_sentence(self):
        with self.assertRaisesRegex(Refused, "is not there yet"):
            files.read_json(self.tmp / "none.json")
        (self.tmp / "bad.json").write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(Refused, "is not valid JSON"):
            files.read_json(self.tmp / "bad.json")

    def test_the_file_digest_is_sha256_of_the_bytes(self):
        path = self.tmp / "a.bin"
        path.write_bytes(b"abc")
        expected = "sha256:" + hashlib.sha256(b"abc").hexdigest()
        self.assertEqual(files.file_digest(path), expected)
        self.assertEqual(files.bytes_digest(b"abc"), expected)
        self.assertIsNone(files.file_digest(self.tmp / "none"))

    def test_a_log_written_at_once_is_canonical_lines(self):
        path = self.tmp / "log.jsonl"
        files.write_jsonl(path, [{"b": 1, "a": 2}, {"n": 3}])
        self.assertEqual(path.read_bytes(), b'{"a":2,"b":1}\n{"n":3}\n')


if __name__ == "__main__":
    unittest.main()
