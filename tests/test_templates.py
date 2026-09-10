import datetime as dt
import tempfile
import unittest
from pathlib import Path

from denodo_cli.templates import TemplateError, format_mark, load_block, parse_address, update_mark

SAMPLE = """# Skill

## Templates

### Database

```sql
-- verified: 9.5.1 (стенд, 2026-09-09)
CREATE OR REPLACE DATABASE sales_analytics 'Sales data products' CHARSET DEFAULT;
```

### Folders

```sql
-- unverified: только по документации 9.5
CREATE OR REPLACE FOLDER '/01 - connectivity';
```

```sql
-- verified: 9.5.1 (стенд, 2026-09-09)
CREATE OR REPLACE FOLDER '/02 - integration';
```

### No mark

```sql
SELECT 1 FROM DUAL();
```
"""

INDENTED_SAMPLE = (
    "# Skill\n"
    "\n"
    "## Templates\n"
    "\n"
    "### Wrapped\n"
    "\n"
    "1. Step one:\n"
    "   ```sql\n"
    "   -- verified: 9.5.1 (стенд, 2026-09-09)\n"
    "   SELECT 1 FROM DUAL();\n"
    "```\n"  # closing fence at a different indent (column 0) than the opening one
    "2. Step two.\n"
)

DUPLICATE_SAMPLE = """# Skill

## Templates

### Database

```sql
-- verified: 9.5.1 (стенд, 2026-09-09)
SELECT 1 FROM DUAL();
```

### Database

```sql
-- verified: 9.5.1 (стенд, 2026-09-09)
SELECT 2 FROM DUAL();
```
"""


class ParseAddressTest(unittest.TestCase):
    def test_file_and_section(self):
        self.assertEqual(parse_address("skills/catalog/SKILL.md#Database"),
                         ("skills/catalog/SKILL.md", "Database", 0))

    def test_explicit_block_index(self):
        self.assertEqual(parse_address("skills/catalog/SKILL.md#Folders[1]"),
                         ("skills/catalog/SKILL.md", "Folders", 1))

    def test_address_without_hash_is_an_error(self):
        with self.assertRaises(TemplateError):
            parse_address("skills/catalog/SKILL.md")


class LoadBlockTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "catalog").mkdir(parents=True)
        (self.root / "skills" / "catalog" / "SKILL.md").write_text(SAMPLE, encoding="utf-8")

    def test_body_and_mark_of_the_first_block_in_a_section(self):
        block = load_block(self.root, "skills/catalog/SKILL.md#Database")
        self.assertEqual(block.language, "sql")
        self.assertIn("CREATE OR REPLACE DATABASE sales_analytics", block.body)
        self.assertEqual(block.mark, "verified: 9.5.1 (стенд, 2026-09-09)")
        self.assertEqual(block.section, "Database")

    def test_second_block_of_a_section_is_addressable(self):
        block = load_block(self.root, "skills/catalog/SKILL.md#Folders[1]")
        self.assertIn("'/02 - integration'", block.body)

    def test_unverified_mark_is_reported_as_is(self):
        block = load_block(self.root, "skills/catalog/SKILL.md#Folders")
        self.assertEqual(block.mark, "unverified: только по документации 9.5")

    def test_mark_line_points_at_the_mark_in_the_file(self):
        block = load_block(self.root, "skills/catalog/SKILL.md#Database")
        line = (self.root / "skills/catalog/SKILL.md").read_text(encoding="utf-8").splitlines()[block.mark_line - 1]
        self.assertTrue(line.startswith("-- verified:"))

    def test_missing_section_names_the_file(self):
        with self.assertRaises(TemplateError) as ctx:
            load_block(self.root, "skills/catalog/SKILL.md#No Such Section")
        self.assertIn("No Such Section", str(ctx.exception))
        self.assertIn("SKILL.md", str(ctx.exception))

    def test_missing_file_is_an_error(self):
        with self.assertRaises(TemplateError):
            load_block(self.root, "skills/nope/SKILL.md#Database")

    def test_block_index_out_of_range_is_an_error(self):
        with self.assertRaises(TemplateError):
            load_block(self.root, "skills/catalog/SKILL.md#Database[3]")

    def test_block_without_a_mark_has_none_for_mark_and_mark_line(self):
        block = load_block(self.root, "skills/catalog/SKILL.md#No mark")
        self.assertIsNone(block.mark)
        self.assertIsNone(block.mark_line)


class IndentedFenceTest(unittest.TestCase):
    """A fence nested inside a list item — the opening ``` is not at column 0."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "listy").mkdir(parents=True)
        (self.root / "skills" / "listy" / "SKILL.md").write_text(INDENTED_SAMPLE, encoding="utf-8")

    def test_fence_indented_inside_a_list_item_is_found_and_dedented(self):
        block = load_block(self.root, "skills/listy/SKILL.md#Wrapped")
        self.assertEqual(block.language, "sql")
        self.assertEqual(block.mark, "verified: 9.5.1 (стенд, 2026-09-09)")
        # dedented: no leading spaces left, even though the closing fence was
        # unindented while the opening one (and its body) were indented by three spaces
        self.assertEqual(
            block.body,
            "-- verified: 9.5.1 (стенд, 2026-09-09)\nSELECT 1 FROM DUAL();",
        )


class DuplicateSectionTest(unittest.TestCase):
    """Two headings with the same text make an address ambiguous."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "dup").mkdir(parents=True)
        (self.root / "skills" / "dup" / "SKILL.md").write_text(DUPLICATE_SAMPLE, encoding="utf-8")

    def test_duplicate_section_heading_is_an_error(self):
        with self.assertRaises(TemplateError) as ctx:
            load_block(self.root, "skills/dup/SKILL.md#Database")
        message = str(ctx.exception)
        self.assertIn("Database", message)
        self.assertIn("SKILL.md", message)


class RealSkillFileTest(unittest.TestCase):
    """Regression coverage against the actual repository content, not a fixture."""

    def test_when_you_cannot_see_the_file_section_resolves_and_second_block_carries_a_mark(self):
        root = Path(__file__).resolve().parents[1]
        first = load_block(root, "skills/datasources/SKILL.md#When you cannot see the file")
        self.assertEqual(first.language, "sql")
        self.assertIsNone(first.mark)

        second = load_block(root, "skills/datasources/SKILL.md#When you cannot see the file[1]")
        self.assertEqual(second.language, "sql")
        self.assertEqual(second.mark, "verified: 9.5.1 (стенд, 2026-09-09)")
        self.assertIn("CREATE OR REPLACE DATASOURCE DF ds_crm", second.body)
        # dedented: the raw file indents this fence by three spaces (it lives inside a
        # numbered list), so an un-dedented body would still carry that indentation here
        self.assertTrue(second.body.startswith("-- verified:"))


class UpdateMarkTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "catalog").mkdir(parents=True)
        self.file = self.root / "skills" / "catalog" / "SKILL.md"
        self.file.write_text(SAMPLE, encoding="utf-8")

    def test_format(self):
        self.assertEqual(format_mark("9.5.1", dt.date(2026, 9, 10)), "verified: 9.5.1 (стенд, 2026-09-10)")

    def test_verified_mark_gets_the_new_version_and_date(self):
        block = load_block(self.root, "skills/catalog/SKILL.md#Database")
        self.assertTrue(update_mark(block, version="9.5.1", day=dt.date(2026, 9, 10)))
        text = self.file.read_text(encoding="utf-8")
        self.assertIn("-- verified: 9.5.1 (стенд, 2026-09-10)", text)
        self.assertNotIn("2026-09-09", text.split("### Folders")[0])

    def test_unverified_mark_becomes_verified(self):
        block = load_block(self.root, "skills/catalog/SKILL.md#Folders")
        update_mark(block, version="9.5.1", day=dt.date(2026, 9, 10))
        self.assertIn("-- verified: 9.5.1 (стенд, 2026-09-10)", self.file.read_text(encoding="utf-8"))

    def test_comment_prefix_of_the_channel_is_kept(self):
        bash = self.root / "skills" / "marketplace"
        bash.mkdir(parents=True)
        (bash / "SKILL.md").write_text(
            "### Tag\n\n```bash\n# verified: 9.5.1 (стенд, 2026-09-01)\napi get /x\n```\n", encoding="utf-8")
        block = load_block(self.root, "skills/marketplace/SKILL.md#Tag")
        update_mark(block, version="9.5.1", day=dt.date(2026, 9, 10))
        self.assertIn("# verified: 9.5.1 (стенд, 2026-09-10)", (bash / "SKILL.md").read_text(encoding="utf-8"))

    def test_block_without_a_mark_is_left_alone(self):
        plain = self.root / "skills" / "views"
        plain.mkdir(parents=True)
        (plain / "SKILL.md").write_text("### V\n\n```sql\nSELECT 1;\n```\n", encoding="utf-8")
        block = load_block(self.root, "skills/views/SKILL.md#V")
        self.assertFalse(update_mark(block, version="9.5.1", day=dt.date(2026, 9, 10)))
        self.assertEqual((plain / "SKILL.md").read_text(encoding="utf-8"), "### V\n\n```sql\nSELECT 1;\n```\n")

    def test_trailing_note_after_the_date_is_preserved(self):
        noted = self.root / "skills" / "ds"
        noted.mkdir(parents=True)
        (noted / "SKILL.md").write_text(
            "### D\n\n```sql\n-- verified: 9.5.1 (стенд, 2026-09-09) — against live Oracle\nSELECT 1;\n```\n",
            encoding="utf-8")
        block = load_block(self.root, "skills/ds/SKILL.md#D")
        update_mark(block, version="9.5.1", day=dt.date(2026, 9, 10))
        self.assertIn("-- verified: 9.5.1 (стенд, 2026-09-10) — against live Oracle",
                      (noted / "SKILL.md").read_text(encoding="utf-8"))

    def test_already_up_to_date_mark_returns_false_and_does_not_change_file(self):
        block = load_block(self.root, "skills/catalog/SKILL.md#Database")
        # First update
        self.assertTrue(update_mark(block, version="9.5.1", day=dt.date(2026, 9, 10)))
        file_after_first = self.file.read_text(encoding="utf-8")
        # Second update with same version and day
        self.assertFalse(update_mark(block, version="9.5.1", day=dt.date(2026, 9, 10)))
        file_after_second = self.file.read_text(encoding="utf-8")
        # File must be byte-identical
        self.assertEqual(file_after_first, file_after_second)
