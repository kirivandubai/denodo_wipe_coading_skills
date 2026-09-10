import unittest
from pathlib import Path
import tempfile

from denodo_cli.templates import TemplateError, load_block, parse_address

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
