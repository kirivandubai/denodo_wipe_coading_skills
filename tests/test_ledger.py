import datetime as dt
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from denodo_cli.ledger import Ledger, prune_sessions, session_from_env
from denodo_cli.statements import ObjectRef

NOW = dt.datetime(2026, 10, 6, 9, 0, tzinfo=dt.timezone.utc)
SERVER = "localhost:9996"
VIEW = ObjectRef("view", "sales", "iv_orders", "derived view")


class SessionIdTest(unittest.TestCase):
    def test_explicit_session_wins(self):
        self.assertEqual(session_from_env({"DENODO_SESSION": "ci-42", "CLAUDE_CODE_SESSION_ID": "abc"}),
                         ("ci-42", "DENODO_SESSION"))

    def test_claude_code_session(self):
        self.assertEqual(session_from_env({"CLAUDE_CODE_SESSION_ID": "9e03"}), ("9e03", "CLAUDE_CODE_SESSION_ID"))

    def test_no_session(self):
        self.assertEqual(session_from_env({}), (None, None))
        self.assertEqual(session_from_env({"DENODO_SESSION": "  "}), (None, None))


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "sessions"
        self.ledger = Ledger(self.dir, "9e03eff8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_touch_creates_a_private_file_with_the_start_time(self):
        started = self.ledger.touch(NOW)
        self.assertEqual(started, NOW)
        self.assertEqual(stat.S_IMODE(os.stat(self.ledger.path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.dir).st_mode), 0o700)
        later = self.ledger.touch(NOW + dt.timedelta(hours=1))
        self.assertEqual(later, NOW, "the start is the first touch, not the latest")

    def test_a_session_id_cannot_climb_out_of_the_directory(self):
        ledger = Ledger(self.dir, "../../etc/x")
        self.assertEqual(ledger.path.parent, self.dir)

    def test_created_object_is_found_by_its_identity(self):
        self.ledger.record_created(SERVER, VIEW, internal_id="_a1", source="model/v.vql",
                                   statement="CREATE OR REPLACE VIEW iv_orders …", now=NOW)
        entry = self.ledger.find(SERVER, ObjectRef("view", "SALES", "IV_Orders"))
        self.assertEqual(entry["internal_id"], "_a1")
        self.assertEqual(entry["status"], "present")
        self.assertEqual(entry["kind"], "derived view")
        self.assertIsNone(self.ledger.find("otherhost:9996", VIEW))

    def test_recording_twice_keeps_one_entry(self):
        for _ in range(2):
            self.ledger.record_created(SERVER, VIEW, internal_id="_a1", source=None, statement="", now=NOW)
        self.assertEqual(len(self.ledger.objects(SERVER)), 1)

    def test_a_dropped_object_is_no_longer_present_but_remembered(self):
        self.ledger.record_created(SERVER, VIEW, internal_id="_a1", source=None, statement="", now=NOW)
        self.ledger.record_dropped(SERVER, VIEW, now=NOW)
        self.assertIsNone(self.ledger.find(SERVER, VIEW))
        self.assertEqual(self.ledger.former(SERVER, VIEW)["status"], "dropped")

    def test_a_rename_moves_the_name_and_keeps_the_history(self):
        self.ledger.record_created(SERVER, VIEW, internal_id="_a1", source=None, statement="", now=NOW)
        self.ledger.record_renamed(SERVER, VIEW, "orders_report", now=NOW)
        renamed = ObjectRef("view", "sales", "orders_report")
        self.assertEqual(self.ledger.find(SERVER, renamed)["names"], ["iv_orders", "orders_report"])
        self.assertIsNone(self.ledger.find(SERVER, VIEW))
        self.assertEqual(self.ledger.former(SERVER, VIEW)["name"], "orders_report")

    def test_drop_and_rename_of_unknown_objects_change_nothing(self):
        self.ledger.record_dropped(SERVER, VIEW, now=NOW)
        self.ledger.record_renamed(SERVER, VIEW, "x", now=NOW)
        self.assertEqual(self.ledger.objects(SERVER), [])

    def test_recreated_after_a_drop_is_a_new_entry(self):
        self.ledger.record_created(SERVER, VIEW, internal_id="_a1", source=None, statement="", now=NOW)
        self.ledger.record_dropped(SERVER, VIEW, now=NOW)
        self.ledger.record_created(SERVER, VIEW, internal_id="_b2", source=None, statement="", now=NOW)
        self.assertEqual(self.ledger.find(SERVER, VIEW)["internal_id"], "_b2")
        self.assertEqual(len(self.ledger.objects(SERVER)), 2)

    def test_the_file_is_json(self):
        self.ledger.record_created(SERVER, VIEW, internal_id="_a1", source=None, statement="", now=NOW)
        doc = json.loads(self.ledger.path.read_text())
        self.assertEqual(doc["session"], "9e03eff8")
        self.assertIn(SERVER, doc["servers"])

    def test_a_damaged_file_is_set_aside_not_trusted(self):
        self.dir.mkdir(parents=True)
        self.ledger.path.write_text("{not json")
        self.assertEqual(self.ledger.objects(SERVER), [])
        self.ledger.record_created(SERVER, VIEW, internal_id="_a1", source=None, statement="", now=NOW)
        self.assertEqual(len(self.ledger.objects(SERVER)), 1)


class PruneTest(unittest.TestCase):
    def test_old_session_files_go(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            old, fresh = directory / "old.json", directory / "fresh.json"
            for path in (old, fresh):
                path.write_text("{}")
            month_ago = (NOW - dt.timedelta(days=31)).timestamp()
            os.utime(old, (month_ago, month_ago))
            os.utime(fresh, (NOW.timestamp(), NOW.timestamp()))
            prune_sessions(directory, NOW)
            self.assertFalse(old.exists())
            self.assertTrue(fresh.exists())


if __name__ == "__main__":
    unittest.main()
