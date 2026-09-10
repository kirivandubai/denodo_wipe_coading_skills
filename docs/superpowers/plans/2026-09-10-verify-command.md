# `scripts/denodo verify` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Повторяемый прогон шаблонов навыков на живом стенде: одна сквозная цепочка от базы до ассоциации, с уборкой за собой и простановкой пометок `verified:`.

**Architecture:** План цепочки лежит в `verification/chain.toml`, механика — в `denodo_cli/commands/verify.py`. Шаг ссылается на блок навыка адресом `skills/<навык>/SKILL.md#<Заголовок раздела>`, тело извлекается из markdown и правится подстановкой точных строк. VQL исполняется через существующий `commands.vql.run_statements`, HTTP — через `commands.api.api_call`; ничего своего для транспорта и классификации разрушительных операций не заводится.

**Tech Stack:** Python 3.11+ (только стандартная библиотека: `tomllib`, `re`, `pathlib`, `unittest`), существующий слой исполнения `scripts/denodo_cli/`.

**Spec:** `docs/superpowers/specs/2026-09-04-denodo-skills-design.md`, раздел 11.1 (обновлён в этой же ветке, коммит `729b5f4`).

## Global Constraints

- **Целевая версия Denodo — только 9.5.** Развилок по версиям нет.
- **`scripts/denodo` (launcher) — только стандартная библиотека.** Новый код живёт в `denodo_cli/`, launcher не трогаем.
- **Креденшелы не попадают ни в репозиторий, ни в аргументы команд.** В манифесте и в тестах фигурирует только имя профиля.
- **В репозитории нет клиентских данных.** Все имена в манифесте — из навыков и демо-набора стенда.
- **На стенде пишем только в свою базу.** Прогон создаёт `denodo_skills_test` и живёт в ней; единственные объекты вне базы — серверные теги VDP и (под флагом) объекты маркетплейса, и оба убираются явно.
- **Каждая команда печатает ровно один JSON-документ на stdout.** Коды выхода: `0` ok, `1` сервер отказал, `2` usage/config/отказ по безопасности, `3` не установлен драйверный стек.
- **Тесты гоняются без зависимостей:** `PYTHONPATH=scripts python3 -m unittest discover -s tests -t .`
- **Интеграционные тесты включаются переменной `DENODO_TEST_ENV`** и пропускаются на production-профиле.
- **Язык кода, комментариев и текста навыков — английский.** Проектная документация (`docs/`, `CLAUDE.md`, этот план) — русская.

## File Structure

| Файл | Ответственность |
|---|---|
| `scripts/denodo_cli/templates.py` (создать) | Адресация блока в markdown, извлечение тела, чтение и перезапись строки-пометки. Ничего не знает про Denodo. |
| `scripts/denodo_cli/commands/verify.py` (создать) | Загрузка манифеста, подстановки, исполнение шагов, отчёт, уборка. |
| `verification/chain.toml` (создать) | План цепочки: шаги, адреса, подстановки, проверки. Данные, не код. |
| `scripts/denodo_cli/cli.py` (изменить) | Ветка `verify` в парсере и в `_dispatch`. |
| `tests/test_templates.py` (создать) | Юниты на адресацию и пометки. |
| `tests/test_commands_verify.py` (создать) | Юниты на манифест, подстановки, исполнение и уборку — на фейковых транспортах. |
| `tests/integration/test_verify_chain.py` (создать) | Прогон настоящей цепочки против стенда. |
| `docs/TASKS.md` (изменить) | T12 → сделано, с честным разделом «что осталось». |

---

### Task 1: Адресация и извлечение блока навыка

**Files:**
- Create: `scripts/denodo_cli/templates.py`
- Test: `tests/test_templates.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `TemplateBlock` (поля `path: Path`, `section: str`, `index: int`, `language: str`, `body: str`, `mark_line: int | None`, `mark: str | None`), `parse_address(address: str) -> tuple[str, str, int]`, `load_block(root: Path, address: str) -> TemplateBlock`, `TemplateError(Exception)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_templates.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=scripts python3 -m unittest tests.test_templates -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'denodo_cli.templates'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/denodo_cli/templates.py
"""Addressing a code block inside a skill file.

A template lives in the skill text, not in a copy: ``verify`` reads the block the agent
reads. The address is the file, the heading of the section and the block's index inside
that section — ``skills/views/SKILL.md#Derived view``, ``…#Folders[1]`` for the second
block of a section. A broken address fails loudly; a copy would have drifted silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MARK = re.compile(r"^\s*(?:--|#|//)\s*((?:un)?verified:.*)$")
FENCE = re.compile(r"^```(\w*)\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
ADDRESS = re.compile(r"^(?P<path>[^#]+)#(?P<section>[^\[\]]+?)(?:\[(?P<index>\d+)\])?$")


class TemplateError(Exception):
    """A block address does not resolve. Message is user-facing."""


@dataclass(frozen=True)
class TemplateBlock:
    path: Path
    section: str
    index: int
    language: str
    body: str               # block content, mark line included
    first_line: int         # 1-based line of the first content line
    mark_line: int | None   # 1-based line of the mark, None when the block carries none
    mark: str | None        # "verified: 9.5.1 (стенд, 2026-09-09)" or None


def parse_address(address: str) -> tuple[str, str, int]:
    match = ADDRESS.match(address.strip())
    if not match:
        raise TemplateError(
            f"template address {address!r} is not <file>#<section> or <file>#<section>[<n>]")
    return match["path"], match["section"], int(match["index"] or 0)


def load_block(root: Path, address: str) -> TemplateBlock:
    relative, section, index = parse_address(address)
    path = Path(root) / relative
    if not path.is_file():
        raise TemplateError(f"template file not found: {relative}")
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks = _blocks_of_section(lines, section)
    if not blocks:
        raise TemplateError(f"section {section!r} not found in {relative}")
    if index >= len(blocks):
        raise TemplateError(
            f"section {section!r} in {relative} has {len(blocks)} block(s), asked for [{index}]")
    language, first_line, body_lines = blocks[index]
    mark_line = mark = None
    for offset, line in enumerate(body_lines):
        found = MARK.match(line)
        if found:
            mark_line, mark = first_line + offset, found.group(1).strip()
            break
    return TemplateBlock(path=path, section=section, index=index, language=language,
                         body="\n".join(body_lines), first_line=first_line,
                         mark_line=mark_line, mark=mark)


def _blocks_of_section(lines: list[str], section: str) -> list[tuple[str, int, list[str]]]:
    """Fenced blocks of the section whose heading text equals ``section``."""
    blocks: list[tuple[str, int, list[str]]] = []
    depth: int | None = None
    inside = False
    language, start, body = "", 0, []
    for number, line in enumerate(lines, start=1):
        heading = HEADING.match(line)
        if heading and not inside:
            level, text = len(heading.group(1)), heading.group(2)
            if text == section:      # entering the section: start collecting from scratch
                depth, blocks = level, []
            elif depth is not None and level <= depth:
                depth = None         # a sibling or higher heading closes the section
            continue
        if depth is None:
            continue
        fence = FENCE.match(line)
        if fence and not inside:
            inside, language, start, body = True, fence.group(1), number + 1, []
        elif inside and line.startswith("```"):
            inside = False
            blocks.append((language, start, body))
        elif inside:
            body.append(line)
    return blocks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=scripts python3 -m unittest tests.test_templates -v`
Expected: PASS — семь тестов.

- [ ] **Step 5: Run the whole suite**

Run: `PYTHONPATH=scripts python3 -m unittest discover -s tests -t . -q`
Expected: OK, ничего не сломано.

- [ ] **Step 6: Commit**

```bash
git add scripts/denodo_cli/templates.py tests/test_templates.py
git commit -m "feat(verify): адресация блока навыка по файлу, разделу и номеру"
```

---

### Task 2: Перезапись пометки верификации

**Files:**
- Modify: `scripts/denodo_cli/templates.py`
- Test: `tests/test_templates.py`

**Interfaces:**
- Consumes: `TemplateBlock`, `load_block` из Task 1.
- Produces: `format_mark(version: str, day: date) -> str`, `update_mark(block: TemplateBlock, *, version: str, day: date) -> bool` — переписывает строку пометки в файле, возвращает `False`, если у блока пометки нет или текст уже совпадает.

- [ ] **Step 1: Write the failing test**

```python
# добавить в tests/test_templates.py
import datetime as dt

from denodo_cli.templates import format_mark, update_mark


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=scripts python3 -m unittest tests.test_templates.UpdateMarkTest -v`
Expected: FAIL — `ImportError: cannot import name 'format_mark'`

- [ ] **Step 3: Write minimal implementation**

```python
# добавить в scripts/denodo_cli/templates.py
import datetime as dt

MARK_BODY = re.compile(r"^(?:un)?verified:\s*[^(]*\((?P<place>[^,]+),\s*[^)]*\)(?P<note>.*)$")


def format_mark(version: str, day: dt.date) -> str:
    return f"verified: {version} (стенд, {day.isoformat()})"


def update_mark(block: TemplateBlock, *, version: str, day: dt.date) -> bool:
    """Rewrite the block's mark in place. False when there is nothing to rewrite."""
    if block.mark_line is None or block.mark is None:
        return False
    lines = block.path.read_text(encoding="utf-8").splitlines(keepends=True)
    old = lines[block.mark_line - 1]
    prefix = old[: len(old) - len(old.lstrip())]
    comment = "#" if old.lstrip().startswith("#") else ("//" if old.lstrip().startswith("//") else "--")
    note = ""
    parsed = MARK_BODY.match(block.mark)
    if parsed:
        note = parsed["note"]
    new = f"{prefix}{comment} {format_mark(version, day)}{note}\n"
    if new == old:
        return False
    lines[block.mark_line - 1] = new
    block.path.write_text("".join(lines), encoding="utf-8")
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=scripts python3 -m unittest tests.test_templates -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/denodo_cli/templates.py tests/test_templates.py
git commit -m "feat(verify): перезапись пометки verified с сохранением канала и примечания"
```

---

### Task 3: Манифест цепочки и подстановки

**Files:**
- Create: `scripts/denodo_cli/commands/verify.py`
- Test: `tests/test_commands_verify.py`

**Interfaces:**
- Consumes: `templates.load_block`, `templates.TemplateError`.
- Produces: `Step` (поля `id: str`, `kind: str`, `channel: str`, `address: str | None`, `vql: str | None`, `calls: list[int]`, `substitute: dict[str, str]`, `capture: dict[str, str]`, `check: str | None`, `expect: str`, `marketplace: bool`), `Chain` (поля `values: dict[str, str]`, `steps: list[Step]`), `load_chain(path: Path) -> Chain`, `render(text: str, substitute: dict[str, str], values: dict[str, str]) -> str`, `ChainError(Exception)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_commands_verify.py
import tempfile
import unittest
from pathlib import Path

from denodo_cli.commands.verify import ChainError, load_chain, render

MANIFEST = """
[values]
database = "denodo_skills_test"
csv_dir = "/opt/denodo/demos/csv"

[[step]]
id = "database"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Database"
substitute = { sales_analytics = "{database}" }
check = "SELECT db_name FROM GET_DATABASES() WHERE db_name = '{database}'"

[[step]]
id = "fixture-base-views"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
expect = "no rows"

[[step]]
id = "mp-tag"
kind = "template"
channel = "http"
address = "skills/marketplace/SKILL.md#Tag, with an assignment"
marketplace = true
calls = [0, 1]
capture = { tag_id = "id" }
"""


class LoadChainTest(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "chain.toml"
        self.path.write_text(MANIFEST, encoding="utf-8")

    def test_values_and_step_order(self):
        chain = load_chain(self.path)
        self.assertEqual(chain.values["database"], "denodo_skills_test")
        self.assertEqual([s.id for s in chain.steps], ["database", "fixture-base-views", "mp-tag"])

    def test_defaults(self):
        chain = load_chain(self.path)
        first, fixture, http = chain.steps
        self.assertEqual(first.expect, "rows")          # default
        self.assertEqual(fixture.expect, "no rows")
        self.assertFalse(first.marketplace)
        self.assertTrue(http.marketplace)
        self.assertEqual(http.calls, [0, 1])
        self.assertEqual(http.capture, {"tag_id": "id"})
        self.assertEqual(first.substitute, {"sales_analytics": "{database}"})

    def test_template_step_without_address_is_rejected(self):
        self.path.write_text('[[step]]\nid = "x"\nkind = "template"\nchannel = "vql"\n', encoding="utf-8")
        with self.assertRaises(ChainError) as ctx:
            load_chain(self.path)
        self.assertIn("address", str(ctx.exception))

    def test_fixture_step_without_body_is_rejected(self):
        self.path.write_text('[[step]]\nid = "x"\nkind = "fixture"\nchannel = "vql"\n', encoding="utf-8")
        with self.assertRaises(ChainError):
            load_chain(self.path)

    def test_unknown_kind_is_rejected(self):
        self.path.write_text('[[step]]\nid = "x"\nkind = "magic"\nchannel = "vql"\n', encoding="utf-8")
        with self.assertRaises(ChainError):
            load_chain(self.path)

    def test_duplicate_step_id_is_rejected(self):
        self.path.write_text(
            '[[step]]\nid = "x"\nkind = "fixture"\nchannel = "vql"\nvql = "SELECT 1"\n'
            '[[step]]\nid = "x"\nkind = "fixture"\nchannel = "vql"\nvql = "SELECT 2"\n', encoding="utf-8")
        with self.assertRaises(ChainError):
            load_chain(self.path)


class RenderTest(unittest.TestCase):
    def test_exact_string_is_replaced_everywhere(self):
        body = "CREATE DATABASE sales_analytics;\nCONNECT DATABASE sales_analytics;"
        out = render(body, {"sales_analytics": "{database}"}, {"database": "denodo_skills_test"})
        self.assertNotIn("sales_analytics", out)
        self.assertEqual(out.count("denodo_skills_test"), 2)

    def test_missing_substitution_fails_loudly(self):
        with self.assertRaises(ChainError) as ctx:
            render("SELECT 1", {"sales_analytics": "{database}"}, {"database": "d"})
        self.assertIn("sales_analytics", str(ctx.exception))

    def test_unknown_value_name_fails_loudly(self):
        with self.assertRaises(ChainError) as ctx:
            render("x sales_analytics", {"sales_analytics": "{nope}"}, {"database": "d"})
        self.assertIn("nope", str(ctx.exception))

    def test_placeholders_in_plain_text_are_filled_too(self):
        out = render("SELECT '{database}'", {}, {"database": "denodo_skills_test"})
        self.assertEqual(out, "SELECT 'denodo_skills_test'")

    def test_a_placeholder_with_no_value_is_left_alone(self):
        out = render("SELECT '{unknown}'", {}, {"database": "d"})
        self.assertEqual(out, "SELECT '{unknown}'")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=scripts python3 -m unittest tests.test_commands_verify -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'denodo_cli.commands.verify'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/denodo_cli/commands/verify.py
"""``verify``: run the v1 chain of skill templates against a stand and clean up.

The plan is data (``verification/chain.toml``), the mechanics are here. A step either
points at a block of a skill (``template`` — the thing being verified) or carries its own
body (``fixture`` — scaffolding that makes the chain reachable). Substitutions are exact
strings, and one that does not occur in the block is an error: silently skipping it would
send the run into somebody else's database.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ("template", "fixture")
CHANNELS = ("vql", "http")
EXPECTS = ("rows", "no rows")
PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


class ChainError(Exception):
    """The manifest is malformed or a substitution does not apply. Message is user-facing."""


@dataclass(frozen=True)
class Step:
    id: str
    kind: str
    channel: str
    address: str | None = None
    vql: str | None = None
    calls: list[int] = field(default_factory=list)
    substitute: dict[str, str] = field(default_factory=dict)
    capture: dict[str, str] = field(default_factory=dict)
    check: str | None = None
    expect: str = "rows"
    marketplace: bool = False


@dataclass(frozen=True)
class Chain:
    values: dict[str, str]
    steps: list[Step]


def load_chain(path: Path) -> Chain:
    try:
        document = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ChainError(f"cannot read chain manifest {path}: {exc}") from exc
    values = {str(k): str(v) for k, v in (document.get("values") or {}).items()}
    steps: list[Step] = []
    seen: set[str] = set()
    for raw in document.get("step") or []:
        step = _step(raw)
        if step.id in seen:
            raise ChainError(f"duplicate step id {step.id!r} in {path}")
        seen.add(step.id)
        steps.append(step)
    if not steps:
        raise ChainError(f"chain manifest {path} has no steps")
    return Chain(values=values, steps=steps)


def _step(raw: dict) -> Step:
    step_id = raw.get("id")
    if not step_id:
        raise ChainError("every step needs an id")
    kind, channel = raw.get("kind"), raw.get("channel")
    if kind not in KINDS:
        raise ChainError(f"step {step_id!r}: kind must be one of {KINDS}, got {kind!r}")
    if channel not in CHANNELS:
        raise ChainError(f"step {step_id!r}: channel must be one of {CHANNELS}, got {channel!r}")
    expect = raw.get("expect", "rows")
    if expect not in EXPECTS:
        raise ChainError(f"step {step_id!r}: expect must be one of {EXPECTS}, got {expect!r}")
    if kind == "template" and not raw.get("address"):
        raise ChainError(f"step {step_id!r}: a template step needs an address")
    if kind == "fixture" and not raw.get("vql"):
        raise ChainError(f"step {step_id!r}: a fixture step needs a vql body")
    return Step(id=step_id, kind=kind, channel=channel, address=raw.get("address"), vql=raw.get("vql"),
                calls=[int(c) for c in raw.get("calls", [])],
                substitute={str(k): str(v) for k, v in (raw.get("substitute") or {}).items()},
                capture={str(k): str(v) for k, v in (raw.get("capture") or {}).items()},
                check=raw.get("check"), expect=expect, marketplace=bool(raw.get("marketplace", False)))


def render(text: str, substitute: dict[str, str], values: dict[str, str]) -> str:
    """Apply exact-string substitutions, then fill ``{value}`` placeholders."""
    out = text
    for needle, replacement in substitute.items():
        if needle not in out:
            raise ChainError(f"substitution {needle!r} does not occur in the block")
        out = out.replace(needle, replacement)
    for name in {m.group(1) for m in PLACEHOLDER.finditer("".join(substitute.values()))}:
        if name not in values:
            raise ChainError(f"substitution refers to unknown value {{{name}}}")
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=scripts python3 -m unittest tests.test_commands_verify -v`
Expected: PASS — одиннадцать тестов.

- [ ] **Step 5: Commit**

```bash
git add scripts/denodo_cli/commands/verify.py tests/test_commands_verify.py
git commit -m "feat(verify): манифест цепочки и подстановка точных строк"
```

---

### Task 4: Исполнение VQL-шагов и отчёт

**Files:**
- Modify: `scripts/denodo_cli/commands/verify.py`
- Test: `tests/test_commands_verify.py`

**Interfaces:**
- Consumes: `Chain`, `Step`, `render`, `templates.load_block`, `commands.vql.run_statements`, `output.envelope`, `vql_split.split_statements`.
- Produces: `run_chain(profile, chain, *, root: Path, vql_factory, rest_factory=None, database: str | None = None, with_marketplace: bool = False, keep: bool = False, update_marks: bool = False, today=None) -> tuple[dict, int]`. Документ: `ok`, `command="verify"`, `env`, `steps[]` (`id`, `kind`, `source`, `channel`, `ok`, `skipped`, `error`, `check`), `summary` (`verified`, `failed`, `skipped`), `cleanup`.

- [ ] **Step 1: Write the failing test**

```python
# добавить в tests/test_commands_verify.py
from denodo_cli.commands.verify import run_chain
from denodo_cli.profiles import Profile
from denodo_cli.transports.base import VqlResult

SKILL_TEXT = """### Database

```sql
-- verified: 9.5.1 (стенд, 2026-09-01)
CREATE OR REPLACE DATABASE sales_analytics 'x';
```

### Boom

```sql
-- verified: 9.5.1 (стенд, 2026-09-01)
CONNECT DATABASE sales_analytics;
BOOM;
```
"""


def profile(**over):
    base = dict(name="lab", host="h", port=29996, database="admin", user="u", password="p",
                production=False, transport="vql_psycopg2", marketplace_url=None, marketplace_server_id=None)
    base.update(over)
    return Profile(**base)


class FakeVql:
    instances = []

    def __init__(self, profile, database=None):
        self.database, self.executed, self.closed = database, [], False
        FakeVql.instances.append(self)

    def execute(self, statement):
        self.executed.append(statement)
        if "BOOM" in statement:
            raise RuntimeError("ERROR:  boom\nDETAIL:  java.sql.SQLException: Syntax error near 'BOOM'\n")
        if statement.upper().startswith(("SELECT", "DESC")):
            rows = [] if "GET_VIEWS" in statement else [["denodo_skills_test"]]
            return VqlResult(statement=statement, columns=["c"], rows=rows)
        return VqlResult(statement=statement, columns=None, rows=None)

    def close(self):
        self.closed = True


class RunChainTest(unittest.TestCase):
    def setUp(self):
        FakeVql.instances.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "catalog").mkdir(parents=True)
        (self.root / "skills" / "catalog" / "SKILL.md").write_text(SKILL_TEXT, encoding="utf-8")
        self.manifest = self.root / "chain.toml"

    def chain(self, text):
        self.manifest.write_text(text, encoding="utf-8")
        return load_chain(self.manifest)

    def test_template_step_runs_the_block_with_substitutions_applied(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "database"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Database"
substitute = { sales_analytics = "{database}" }
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 0)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["command"], "verify")
        self.assertEqual(doc["steps"][0]["id"], "database")
        self.assertEqual(doc["steps"][0]["source"], "skills/catalog/SKILL.md#Database")
        executed = " ".join(FakeVql.instances[0].executed)
        self.assertIn("denodo_skills_test", executed)
        self.assertNotIn("sales_analytics", executed)

    def test_check_is_run_against_the_test_database_and_must_return_rows(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "database"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Database"
substitute = { sales_analytics = "{database}" }
check = "SELECT db_name FROM GET_DATABASES() WHERE db_name = '{database}'"
""")
        doc, _ = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertTrue(doc["steps"][0]["check"]["ok"])
        self.assertEqual(doc["steps"][0]["check"]["row_count"], 1)

    def test_expect_no_rows_passes_on_an_empty_result(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "nothing-invalid"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
check = "SELECT name FROM GET_VIEWS() WHERE input_database_name = '{database}'"
expect = "no rows"
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 0, doc)
        self.assertTrue(doc["steps"][0]["check"]["ok"])

    def test_a_failing_statement_stops_the_chain_and_marks_the_rest_skipped(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "boom"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Boom"
substitute = { sales_analytics = "{database}" }
[[step]]
id = "after"
kind = "fixture"
channel = "vql"
vql = "SELECT 1 FROM DUAL()"
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 1)
        self.assertFalse(doc["ok"])
        self.assertFalse(doc["steps"][0]["ok"])
        self.assertIn("Syntax error", doc["steps"][0]["error"]["message"])
        self.assertTrue(doc["steps"][1]["skipped"])
        self.assertEqual(doc["summary"], {"verified": 0, "failed": 1, "skipped": 1})

    def test_fixture_steps_do_not_count_as_verified(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "fix"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
""")
        doc, _ = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(doc["summary"]["verified"], 0)
        self.assertEqual(doc["steps"][0]["kind"], "fixture")

    def test_marketplace_steps_are_skipped_unless_asked_for(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "mp"
kind = "fixture"
channel = "vql"
vql = "SELECT 1 FROM DUAL()"
marketplace = true
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 0)
        self.assertTrue(doc["steps"][0]["skipped"])
        self.assertEqual(doc["steps"][0]["reason"], "marketplace steps need --with-marketplace")

    def test_a_broken_address_is_a_failed_step_not_a_crash(self):
        chain = self.chain("""
[values]
database = "denodo_skills_test"
[[step]]
id = "gone"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#No Such Section"
""")
        doc, code = run_chain(profile(), chain, root=self.root, vql_factory=FakeVql)
        self.assertEqual(code, 1)
        self.assertIn("No Such Section", doc["steps"][0]["error"]["message"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=scripts python3 -m unittest tests.test_commands_verify.RunChainTest -v`
Expected: FAIL — `ImportError: cannot import name 'run_chain'`

- [ ] **Step 3: Write minimal implementation**

```python
# добавить в scripts/denodo_cli/commands/verify.py
import datetime as dt
from typing import Callable

from . import EXIT_EXECUTION, EXIT_OK
from .vql import run_statements
from ..output import envelope
from ..profiles import Profile
from ..templates import TemplateError, load_block
from ..vql_split import split_statements

MAX_ROWS = 10


def run_chain(
    profile: Profile,
    chain: Chain,
    *,
    root: Path,
    vql_factory: Callable,
    rest_factory: Callable | None = None,
    database: str | None = None,
    with_marketplace: bool = False,
    keep: bool = False,
    update_marks: bool = False,
    today: dt.date | None = None,
) -> tuple[dict, int]:
    values = dict(chain.values)
    if database:
        values["database"] = database
    reports: list[dict] = []
    stop = False
    for step in chain.steps:
        if stop:
            reports.append(_skipped(step, "an earlier step failed"))
            continue
        if step.marketplace and not with_marketplace:
            reports.append(_skipped(step, "marketplace steps need --with-marketplace"))
            continue
        report = _run_step(profile, step, values=values, root=root, vql_factory=vql_factory)
        reports.append(report)
        if not report["ok"]:
            stop = True
    ok = all(r["ok"] for r in reports if not r["skipped"]) and not stop
    doc = envelope(ok, profile, "verify", database=values.get("database"), steps=reports,
                   summary=_summary(reports))
    return doc, EXIT_OK if ok else EXIT_EXECUTION


def _skipped(step: Step, reason: str) -> dict:
    return {"id": step.id, "kind": step.kind, "channel": step.channel, "source": step.address,
            "ok": True, "skipped": True, "reason": reason, "error": None, "check": None}


def _summary(reports: list[dict]) -> dict:
    return {
        "verified": sum(1 for r in reports if r["kind"] == "template" and r["ok"] and not r["skipped"]),
        "failed": sum(1 for r in reports if not r["ok"]),
        "skipped": sum(1 for r in reports if r["skipped"]),
    }


def _run_step(profile, step: Step, *, values: dict[str, str], root: Path, vql_factory) -> dict:
    report = {"id": step.id, "kind": step.kind, "channel": step.channel, "source": step.address,
              "ok": False, "skipped": False, "error": None, "check": None}
    try:
        body = _body(step, root=root, values=values)
    except (TemplateError, ChainError) as exc:
        report["error"] = {"kind": "template", "message": str(exc)}
        return report

    statements = split_statements(body)
    doc, code = run_statements(profile, statements, transport_factory=vql_factory, max_rows=MAX_ROWS)
    report["statements"] = doc.get("statements")
    if code != EXIT_OK:
        failed = (doc.get("statements") or [{}])[doc.get("failed_at") or 0]
        report["error"] = failed.get("error") or doc.get("error")
        return report
    if step.check:
        report["check"] = _run_check(profile, step, values=values, vql_factory=vql_factory)
        report["ok"] = report["check"]["ok"]
        if not report["ok"]:
            report["error"] = report["check"].get("error") or {
                "kind": "check", "message": f"check expected {step.expect}"}
        return report
    report["ok"] = True
    return report


def _body(step: Step, *, root: Path, values: dict[str, str]) -> str:
    if step.kind == "fixture":
        return render(step.vql or "", step.substitute, values)
    block = load_block(root, step.address or "")
    return render(block.body, step.substitute, values)


def _run_check(profile, step: Step, *, values: dict[str, str], vql_factory) -> dict:
    statement = render(step.check or "", {}, values)
    doc, code = run_statements(profile, [statement], transport_factory=vql_factory,
                               max_rows=MAX_ROWS, database=values.get("database"))
    entry = (doc.get("statements") or [{}])[0]
    if code != EXIT_OK:
        return {"ok": False, "statement": statement, "row_count": None, "error": entry.get("error")}
    count = entry.get("row_count") or 0
    ok = count > 0 if step.expect == "rows" else count == 0
    return {"ok": ok, "statement": statement, "row_count": count, "expect": step.expect, "error": None}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=scripts python3 -m unittest tests.test_commands_verify -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/denodo_cli/commands/verify.py tests/test_commands_verify.py
git commit -m "feat(verify): исполнение VQL-шагов цепочки с проверками и отчётом"
```

---

### Task 5: Уборка за собой

**Files:**
- Modify: `scripts/denodo_cli/commands/verify.py`
- Test: `tests/test_commands_verify.py`

**Interfaces:**
- Consumes: `run_chain` из Task 4, `Chain`.
- Produces: секция `[cleanup]` манифеста (`vql: list[str]`), поле `cleanup` в отчёте (`{"ran": bool, "reason": str | None, "statements": [...]}`), параметр `keep: bool` в `run_chain`.

- [ ] **Step 1: Write the failing test**

```python
# добавить в tests/test_commands_verify.py
class CleanupTest(unittest.TestCase):
    def setUp(self):
        FakeVql.instances.clear()
        self.root = Path(tempfile.mkdtemp())
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"

[cleanup]
vql = [
  "DROP DATABASE IF EXISTS {database} CASCADE",
  "DROP TAG IF EXISTS {tag_prefix}pii",
]

[[step]]
id = "fix"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
""", encoding="utf-8")
        self.chain = load_chain(self.manifest)

    def test_cleanup_runs_after_a_successful_chain(self):
        doc, code = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql,
                              values_override={"tag_prefix": "verify_"})
        self.assertEqual(code, 0)
        self.assertTrue(doc["cleanup"]["ran"])
        dropped = " ".join(FakeVql.instances[-1].executed)
        self.assertIn("DROP DATABASE IF EXISTS denodo_skills_test CASCADE", dropped)
        self.assertIn("DROP TAG IF EXISTS verify_pii", dropped)

    def test_cleanup_runs_after_a_failed_chain_too(self):
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(
            'vql = "CONNECT DATABASE {database};"', 'vql = "BOOM"'), encoding="utf-8")
        doc, code = run_chain(profile(), load_chain(self.manifest), root=self.root, vql_factory=FakeVql,
                              values_override={"tag_prefix": "verify_"})
        self.assertEqual(code, 1)
        self.assertTrue(doc["cleanup"]["ran"])

    def test_keep_skips_cleanup_and_says_so(self):
        doc, _ = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql, keep=True,
                           values_override={"tag_prefix": "verify_"})
        self.assertFalse(doc["cleanup"]["ran"])
        self.assertIn("--keep", doc["cleanup"]["reason"])
        self.assertNotIn("DROP DATABASE", " ".join(FakeVql.instances[-1].executed))

    def test_a_failing_cleanup_statement_is_reported_and_the_rest_still_run(self):
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(
            '"DROP TAG IF EXISTS {tag_prefix}pii",', '"DROP TAG BOOM", "DROP TAG IF EXISTS x",'),
            encoding="utf-8")
        doc, code = run_chain(profile(), load_chain(self.manifest), root=self.root, vql_factory=FakeVql,
                              values_override={"tag_prefix": "verify_"})
        self.assertEqual(code, 1)                       # уборка не убралась — это провал прогона
        self.assertTrue(doc["cleanup"]["ran"])
        kinds = [s["ok"] for s in doc["cleanup"]["statements"]]
        self.assertEqual(kinds, [True, False, True])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=scripts python3 -m unittest tests.test_commands_verify.CleanupTest -v`
Expected: FAIL — `TypeError: run_chain() got an unexpected keyword argument 'values_override'`

- [ ] **Step 3: Write minimal implementation**

В `load_chain` добавить чтение секции: `cleanup = [str(s) for s in (document.get("cleanup") or {}).get("vql", [])]`, поле `cleanup: list[str]` в `Chain`. В `run_chain` добавить параметр `values_override: dict[str, str] | None = None` (сливается в `values` после `database`) и уборку в `finally`:

```python
    finally_report = _cleanup(profile, chain, values=values, vql_factory=vql_factory, keep=keep)
    ok = ok and (finally_report["ran"] is False or all(s["ok"] for s in finally_report["statements"]))
    doc = envelope(ok, profile, "verify", database=values.get("database"), steps=reports,
                   summary=_summary(reports), cleanup=finally_report)
```

```python
def _cleanup(profile, chain: Chain, *, values: dict[str, str], vql_factory, keep: bool) -> dict:
    """Always runs, including after a failure: a run that did not clean up must say so."""
    if keep:
        return {"ran": False, "reason": "--keep was given; objects were left on the stand",
                "statements": []}
    if not chain.cleanup:
        return {"ran": False, "reason": "the manifest has no cleanup section", "statements": []}
    statements = [render(s, {}, values) for s in chain.cleanup]
    doc, _ = run_statements(profile, statements, transport_factory=vql_factory, max_rows=MAX_ROWS,
                            allow_destructive=True, continue_on_error=True)
    return {"ran": True, "reason": None,
            "statements": [{"statement": s["statement"], "ok": s["ok"], "error": s["error"]}
                           for s in doc.get("statements", [])]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=scripts python3 -m unittest tests.test_commands_verify -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/denodo_cli/commands/verify.py tests/test_commands_verify.py
git commit -m "feat(verify): уборка выполняется всегда и попадает в отчёт"
```

---

### Task 6: Подкоманда `denodo verify` в CLI

**Files:**
- Modify: `scripts/denodo_cli/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_chain`, `run_chain`, `ChainError`.
- Produces: `denodo verify [--env ENV] [--chain FILE] [--database DB] [--with-marketplace] [--keep] [--update-marks]`; путь манифеста по умолчанию — `verification/chain.toml` рядом с корнем репозитория (`Path(__file__).resolve().parents[2]`).

- [ ] **Step 1: Write the failing test**

```python
# добавить в tests/test_cli.py
class VerifyCommandTest(unittest.TestCase):
    def test_parser_accepts_the_flags(self):
        args = build_parser().parse_args(["verify", "--env", "lab", "--with-marketplace", "--keep",
                                          "--update-marks", "--chain", "verification/chain.toml"])
        self.assertEqual(args.group, "verify")
        self.assertTrue(args.with_marketplace)
        self.assertTrue(args.keep)
        self.assertTrue(args.update_marks)
        self.assertEqual(args.chain, "verification/chain.toml")

    def test_defaults(self):
        args = build_parser().parse_args(["verify", "--env", "lab"])
        self.assertFalse(args.with_marketplace)
        self.assertFalse(args.keep)
        self.assertFalse(args.update_marks)
        self.assertIsNone(args.chain)

    def test_a_malformed_manifest_is_a_usage_error_in_json(self):
        path = Path(tempfile.mkdtemp()) / "chain.toml"
        path.write_text("[[step]]\nid = 'x'\nkind = 'magic'\nchannel = 'vql'\n", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["verify", "--env", "nonexistent-profile", "--chain", str(path)])
        doc = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(doc["ok"])
        self.assertIn(doc["error"]["kind"], ("config", "usage"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=scripts python3 -m unittest tests.test_cli.VerifyCommandTest -v`
Expected: FAIL — `UsageError: invalid choice: 'verify'`

- [ ] **Step 3: Write minimal implementation**

В `build_parser()` после блока `env`:

```python
    verify = top.add_parser("verify", parents=[env_opt],
                            help="run the chain of skill templates against a stand and clean up")
    verify.add_argument("--chain", help="manifest path (default: verification/chain.toml in the repo)")
    verify.add_argument("--database", help="test database to create and drop (default: from the manifest)")
    verify.add_argument("--with-marketplace", action="store_true",
                        help="also run the Data Marketplace tail; it writes outside your own database")
    verify.add_argument("--keep", action="store_true", help="leave the created objects on the stand")
    verify.add_argument("--update-marks", action="store_true",
                        help="rewrite the verified: mark of every template step that passed")
```

В `_dispatch` перед `raise UsageError("unknown command")`:

```python
    if args.group == "verify":
        repo = Path(__file__).resolve().parents[2]
        manifest = Path(args.chain).expanduser() if args.chain else repo / "verification" / "chain.toml"
        try:
            chain = load_chain(manifest)
        except ChainError as exc:
            raise UsageError(str(exc)) from exc
        return run_chain(profile, chain, root=repo, vql_factory=resolve_vql_factory(profile),
                         rest_factory=resolve_rest_factory(), database=args.database,
                         with_marketplace=args.with_marketplace, keep=args.keep,
                         update_marks=args.update_marks)
```

Импорт: `from .commands.verify import ChainError, load_chain, run_chain`.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=scripts python3 -m unittest discover -s tests -t . -q`
Expected: OK

- [ ] **Step 5: Check the help text by hand**

Run: `scripts/denodo verify --help`
Expected: перечислены `--chain`, `--database`, `--with-marketplace`, `--keep`, `--update-marks`.

- [ ] **Step 6: Commit**

```bash
git add scripts/denodo_cli/cli.py tests/test_cli.py
git commit -m "feat(verify): подкоманда denodo verify с флагами прогона"
```

---

### Task 7: Манифест цепочки v1 и прогон на стенде

**Files:**
- Create: `verification/chain.toml`
- Create: `tests/integration/test_verify_chain.py`

**Interfaces:**
- Consumes: всё предыдущее.
- Produces: рабочий `verification/chain.toml`, покрывающий цепочку `catalog → datasources → фикстура → views → catalog(теги)`.

Содержание манифеста — шаги в порядке зависимостей. Адреса взяты из текущих навыков; заголовки разделов проверены на 2026-09-10.

- [ ] **Step 1: Write the manifest**

```toml
# verification/chain.toml
# The v1 chain, end to end. Bodies of the "template" steps come from the skills themselves
# (address = file#section); "fixture" steps carry their own body and verify nothing — they
# only make the next template reachable. Design spec, section 11.1.

[values]
database = "denodo_skills_test"
csv_dir = "/opt/denodo/demos/csv"
tag_prefix = "verify_"

[cleanup]
vql = [
  "DROP DATABASE IF EXISTS {database} CASCADE",
  "DROP TAG IF EXISTS {tag_prefix}pii",
  "DROP TAG IF EXISTS {tag_prefix}finance_sensitive",
]

[[step]]
id = "database"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Database"
substitute = { sales_analytics = "{database}" }
check = "SELECT db_name FROM GET_DATABASES() WHERE db_name = '{database}'"

[[step]]
id = "folders"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Folders"
substitute = { sales_analytics = "{database}" }
check = "SELECT name FROM GET_ELEMENTS() WHERE input_database_name = '{database}' AND type = 'folder'"

[[step]]
id = "df-source"
kind = "template"
channel = "vql"
address = "skills/datasources/SKILL.md#Delimited file (CSV) — DF"
substitute = { sales_analytics = "{database}" }
# no check on rows: the file this template names does not exist on the stand, and that is
# the point — the parser accepts the DDL, only SELECT would fail (spec 11.1)
check = "SELECT name FROM GET_ELEMENTS() WHERE input_database_name = '{database}' AND name = 'bv_crm_customers'"

[[step]]
id = "fixture-base-views"
kind = "fixture"
channel = "vql"
check = "SELECT COUNT(*) AS n FROM bv_income_band"
vql = """
CONNECT DATABASE {database};

CREATE OR REPLACE DATASOURCE DF ds_demo_csv
    FOLDER = '/01 - connectivity'
    IGNOREMATCHINGERRORS = FALSE
    ROUTE LOCAL 'LocalConnection' '{csv_dir}/income_band.csv'
    CHARSET = 'UTF-8'
    COLUMNDELIMITER = ','
    HEADER = TRUE;

CREATE OR REPLACE WRAPPER DF wr_income_band
    FOLDER = '/01 - connectivity'
    DATASOURCENAME = ds_demo_csv
    OUTPUTSCHEMA (
        ib_income_band_sk = '"IB_INCOME_BAND_SK"',
        ib_lower_bound = '"IB_LOWER_BOUND"',
        ib_upper_bound = '"IB_UPPER_BOUND"'
    );

CREATE OR REPLACE TABLE bv_income_band I18N us_pst (
        ib_income_band_sk:int, ib_lower_bound:int, ib_upper_bound:int
    )
    FOLDER = '/01 - connectivity'
    CACHE OFF
    TIMETOLIVEINCACHE DEFAULT
    ADD SEARCHMETHOD wr_income_band (
        OUTPUTLIST ( ib_income_band_sk, ib_lower_bound, ib_upper_bound )
        WRAPPER (df wr_income_band)
    );

CREATE OR REPLACE DATASOURCE DF ds_demo_households
    FOLDER = '/01 - connectivity'
    IGNOREMATCHINGERRORS = FALSE
    ROUTE LOCAL 'LocalConnection' '{csv_dir}/household_demographics.csv'
    CHARSET = 'UTF-8'
    COLUMNDELIMITER = ','
    HEADER = TRUE;

CREATE OR REPLACE WRAPPER DF wr_household_demographics
    FOLDER = '/01 - connectivity'
    DATASOURCENAME = ds_demo_households
    OUTPUTSCHEMA (
        hd_demo_sk = '"HD_DEMO_SK"',
        hd_income_band_sk = '"HD_INCOME_BAND_SK"',
        hd_buy_potential = '"HD_BUY_POTENTIAL"',
        hd_dep_count = '"HD_DEP_COUNT"',
        hd_vehicle_count = '"HD_VEHICLE_COUNT"'
    );

CREATE OR REPLACE TABLE bv_household_demographics I18N us_pst (
        hd_demo_sk:int, hd_income_band_sk:int, hd_buy_potential:text,
        hd_dep_count:int, hd_vehicle_count:int
    )
    FOLDER = '/01 - connectivity'
    CACHE OFF
    TIMETOLIVEINCACHE DEFAULT
    ADD SEARCHMETHOD wr_household_demographics (
        OUTPUTLIST ( hd_demo_sk, hd_income_band_sk, hd_buy_potential, hd_dep_count, hd_vehicle_count )
        WRAPPER (df wr_household_demographics)
    );
"""

[[step]]
id = "derived-views"
kind = "template"
channel = "vql"
address = "skills/views/SKILL.md#Derived view"
substitute = { sales_analytics = "{database}" }
check = "SELECT COUNT(*) AS n FROM household_income_by_band"

[[step]]
id = "interface-view"
kind = "template"
channel = "vql"
address = "skills/views/SKILL.md#Interface view — a contract you can re-implement"
substitute = { sales_analytics = "{database}" }
check = "SELECT household_sk FROM household_income LIMIT 10"

[[step]]
id = "association"
kind = "template"
channel = "vql"
address = "skills/views/SKILL.md#Association — the relationship, recorded"
substitute = { sales_analytics = "{database}" }
check = "SELECT association_name FROM GET_ASSOCIATIONS() WHERE input_database_name = '{database}' AND input_type = 'views' AND valid = true"

[[step]]
id = "tags"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Tags, with their assignments"
substitute = { sales_analytics = "{database}", "CREATE OR REPLACE TAG pii" = "CREATE OR REPLACE TAG {tag_prefix}pii", "CREATE OR REPLACE TAG finance_sensitive" = "CREATE OR REPLACE TAG {tag_prefix}finance_sensitive", "{database}.customer.email" = "{database}.household_income.buy_potential", "{database}.customer.phone" = "{database}.household_income.household_sk", "{database}.order_summary" = "{database}.household_income_by_band" }
check = "SELECT tag_name FROM GET_VIEW_TAGS() WHERE input_database_name = '{database}'"

[[step]]
id = "nothing-invalid"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
check = "SELECT name FROM GET_VIEWS() WHERE input_database_name = '{database}' AND input_retrieve_invalid_views_only = true"
expect = "no rows"
```

Замечание для исполнителя: подстановки в шаге `tags` применяются по очереди, поэтому строки с `{database}` в левой части сработают только после того, как `sales_analytics` уже заменён. Порядок ключей в TOML-таблице сохраняется, `sales_analytics` стоит первым — проверить это тестом Task 3 (`test_exact_string_is_replaced_everywhere`) недостаточно, поэтому в Task 7 есть отдельный шаг прогона на стенде.

- [ ] **Step 2: Run the chain against the stand, keeping the objects**

Run:
```bash
PYTHONPATH=scripts uv run --with denodo-sqlalchemy --with psycopg2-binary \
  scripts/denodo verify --env lab --keep
```
Expected: `"ok": true`, в `summary` — `verified` не меньше 6, `failed: 0`. Если шаг упал — читать `steps[].error.message`, править манифест (не навык), повторять.

- [ ] **Step 3: Read the objects back by hand**

Run:
```bash
scripts/denodo vql run --env lab --database denodo_skills_test \
  -e "SELECT name, type, subtype FROM GET_ELEMENTS() WHERE input_database_name = 'denodo_skills_test'"
```
Expected: база, папки, оба источника, обёртки, базовые представления, `iv_household_income`, `household_income_by_band`, `household_income`, ассоциация.

- [ ] **Step 4: Run the chain again without `--keep` and confirm it cleans up**

Run:
```bash
PYTHONPATH=scripts uv run --with denodo-sqlalchemy --with psycopg2-binary \
  scripts/denodo verify --env lab
scripts/denodo vql run --env lab -e "SELECT db_name FROM GET_DATABASES() WHERE db_name = 'denodo_skills_test'"
scripts/denodo vql run --env lab -e "LIST TAGS"
```
Expected: первый вызов `"ok": true` и `cleanup.ran: true`; второй — ноль строк; в `LIST TAGS` нет `verify_pii` и `verify_finance_sensitive`.

- [ ] **Step 5: Write the integration test**

```python
# tests/integration/test_verify_chain.py
"""The v1 chain against a live stand.

Skipped unless ``DENODO_TEST_ENV`` names a non-production profile. Creates and drops
``denodo_skills_test`` and the two ``verify_`` tags — nothing else.

Run:  DENODO_TEST_ENV=lab PYTHONPATH=scripts uv run --with denodo-sqlalchemy \
          --with psycopg2-binary python -m unittest tests.integration.test_verify_chain -v
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from denodo_cli.commands.verify import load_chain, run_chain
from denodo_cli.profiles import load_profile
from denodo_cli.transports import get_vql_transport

ENV = os.environ.get("DENODO_TEST_ENV")
REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(ENV, "DENODO_TEST_ENV not set")
class VerifyChainTest(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile(ENV)
        if self.profile.production:
            self.skipTest("refusing to run the chain on a production profile")
        self.chain = load_chain(REPO / "verification" / "chain.toml")

    def test_the_whole_chain_passes_and_cleans_up(self):
        doc, code = run_chain(self.profile, self.chain, root=REPO,
                              vql_factory=get_vql_transport(self.profile.transport))
        self.assertEqual(code, 0, [s for s in doc["steps"] if not s["ok"]])
        self.assertGreaterEqual(doc["summary"]["verified"], 6)
        self.assertEqual(doc["summary"]["failed"], 0)
        self.assertTrue(doc["cleanup"]["ran"])
        self.assertTrue(all(s["ok"] for s in doc["cleanup"]["statements"]))

    def test_the_test_database_is_gone_afterwards(self):
        transport = get_vql_transport(self.profile.transport)(self.profile)
        try:
            result = transport.execute(
                "SELECT db_name FROM GET_DATABASES() WHERE db_name = 'denodo_skills_test'")
        finally:
            transport.close()
        self.assertEqual(result.rows, [])

    def test_a_second_run_is_green_too(self):
        doc, code = run_chain(self.profile, self.chain, root=REPO,
                              vql_factory=get_vql_transport(self.profile.transport))
        self.assertEqual(code, 0, [s for s in doc["steps"] if not s["ok"]])
```

- [ ] **Step 6: Run the integration test**

Run:
```bash
DENODO_TEST_ENV=lab PYTHONPATH=scripts uv run --with denodo-sqlalchemy --with psycopg2-binary \
  python -m unittest tests.integration.test_verify_chain -v
```
Expected: три теста, OK.

- [ ] **Step 7: Commit**

```bash
git add verification/chain.toml tests/integration/test_verify_chain.py
git commit -m "feat(verify): манифест цепочки v1 и интеграционный прогон на стенде"
```

---

### Task 8: `--update-marks`

**Files:**
- Modify: `scripts/denodo_cli/commands/verify.py`
- Test: `tests/test_commands_verify.py`

**Interfaces:**
- Consumes: `templates.update_mark`, `templates.format_mark`, отчёт из Task 4.
- Produces: поле `mark` в отчёте шага (`{"updated": bool, "text": str}` или `None`), версия сервера читается один раз запросом `SELECT version FROM GET_SERVER_INFO()` перед первым шагом.

- [ ] **Step 1: Write the failing test**

```python
# добавить в tests/test_commands_verify.py
import datetime as dt


class UpdateMarksTest(unittest.TestCase):
    def setUp(self):
        FakeVql.instances.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "catalog").mkdir(parents=True)
        self.skill = self.root / "skills" / "catalog" / "SKILL.md"
        self.skill.write_text(SKILL_TEXT, encoding="utf-8")
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"
[[step]]
id = "database"
kind = "template"
channel = "vql"
address = "skills/catalog/SKILL.md#Database"
substitute = { sales_analytics = "{database}" }
[[step]]
id = "fix"
kind = "fixture"
channel = "vql"
vql = "CONNECT DATABASE {database};"
""", encoding="utf-8")
        self.chain = load_chain(self.manifest)

    def test_marks_are_untouched_without_the_flag(self):
        run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql)
        self.assertIn("2026-09-01", self.skill.read_text(encoding="utf-8"))

    def test_a_passed_template_step_gets_todays_mark(self):
        doc, _ = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql,
                           update_marks=True, today=dt.date(2026, 9, 10))
        self.assertIn("-- verified: 9.5.1 (стенд, 2026-09-10)", self.skill.read_text(encoding="utf-8"))
        self.assertTrue(doc["steps"][0]["mark"]["updated"])

    def test_a_fixture_step_has_no_mark_in_the_report(self):
        doc, _ = run_chain(profile(), self.chain, root=self.root, vql_factory=FakeVql,
                           update_marks=True, today=dt.date(2026, 9, 10))
        self.assertIsNone(doc["steps"][1]["mark"])

    def test_a_failed_step_keeps_its_old_mark(self):
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8").replace(
            "#Database", "#Boom"), encoding="utf-8")
        run_chain(profile(), load_chain(self.manifest), root=self.root, vql_factory=FakeVql,
                  update_marks=True, today=dt.date(2026, 9, 10))
        self.assertIn("2026-09-01", self.skill.read_text(encoding="utf-8"))
        self.assertNotIn("2026-09-10", self.skill.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=scripts python3 -m unittest tests.test_commands_verify.UpdateMarksTest -v`
Expected: FAIL — `KeyError: 'mark'`

- [ ] **Step 3: Write minimal implementation**

В `run_chain` перед циклом:

```python
    version = _server_version(profile, vql_factory) if update_marks else None
    day = today or dt.date.today()
```

```python
def _server_version(profile, vql_factory) -> str:
    doc, code = run_statements(profile, ["SELECT version FROM GET_SERVER_INFO()"],
                               transport_factory=vql_factory, max_rows=1)
    rows = ((doc.get("statements") or [{}])[0]).get("rows") if code == EXIT_OK else None
    if not rows:
        return "9.5"
    return str(rows[0][0]).split()[0]
```

В `_run_step` добавить параметры `update_marks: bool`, `version: str | None`, `day: dt.date` и после успеха:

```python
    report["mark"] = None
    if report["ok"] and step.kind == "template" and update_marks and version:
        block = load_block(root, step.address or "")
        report["mark"] = {"updated": update_mark(block, version=version, day=day),
                          "text": format_mark(version, day)}
```

Импорт: `from ..templates import TemplateError, format_mark, load_block, update_mark`.

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=scripts python3 -m unittest discover -s tests -t . -q`
Expected: OK

- [ ] **Step 5: Try it against the stand and read the diff**

Run:
```bash
PYTHONPATH=scripts uv run --with denodo-sqlalchemy --with psycopg2-binary \
  scripts/denodo verify --env lab --update-marks
git diff --stat skills/
```
Expected: правки только в строках `-- verified:` тех блоков, что прошли; версия — `9.5.1`, дата — сегодняшняя.

- [ ] **Step 6: Commit**

```bash
git add scripts/denodo_cli/commands/verify.py tests/test_commands_verify.py skills/
git commit -m "feat(verify): --update-marks обновляет пометки прошедших шаблонов"
```

---

### Task 9: Маркетплейс-хвост под флагом

**Files:**
- Modify: `scripts/denodo_cli/commands/verify.py`, `verification/chain.toml`
- Test: `tests/test_commands_verify.py`, `tests/integration/test_verify_chain.py`

**Interfaces:**
- Consumes: `commands.api.api_call`, `Step.calls`, `Step.capture`, `Step.marketplace`.
- Produces: `parse_api_calls(body: str) -> list[dict]` — разбор строк `api <method> <path> [--param k=v] [--json '<text>']` из bash-блока навыка; исполнение HTTP-шага; секция `[cleanup] http` (список `{method, path, params}`) с подстановкой захваченных значений.

Разбор вызовов нужен потому, что HTTP-шаблон в навыке — это последовательность команд `api …` вперемешку с комментариями-ответами. Шаг берёт из блока только те вызовы, чьи индексы перечислены в `calls`: в шаблоне тега их четыре, и два из них (`2a` создать / `2b` обновить) — взаимные альтернативы.

- [ ] **Step 1: Write the failing test**

```python
# добавить в tests/test_commands_verify.py
from denodo_cli.commands.verify import parse_api_calls

BASH_BLOCK = """# verified: 9.5.1 (стенд, 2026-09-10)

# 1. does it exist?
api get --env lab /public/api/tag-management/tags --param serverId=306 \\
    --param offset=0 --param limit=50 --param nameFilter=pii
# → {"count":1}

# 2a. missing → create it
api post --env lab /public/api/tags --param serverId=306 \\
    --json '{"name":"pii","description":"Personal data","descriptionType":"TEXT"}'
"""


class ParseApiCallsTest(unittest.TestCase):
    def test_calls_are_found_with_method_path_params_and_body(self):
        calls = parse_api_calls(BASH_BLOCK)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["method"], "GET")
        self.assertEqual(calls[0]["path"], "/public/api/tag-management/tags")
        self.assertEqual(calls[0]["params"]["nameFilter"], "pii")
        self.assertIsNone(calls[0]["json"])
        self.assertEqual(calls[1]["method"], "POST")
        self.assertEqual(calls[1]["json"]["name"], "pii")

    def test_env_flag_is_dropped(self):
        self.assertNotIn("env", parse_api_calls(BASH_BLOCK)[0]["params"])

    def test_comment_lines_are_not_calls(self):
        self.assertTrue(all(c["path"].startswith("/") for c in parse_api_calls(BASH_BLOCK)))


class HttpStepTest(unittest.TestCase):
    class FakeRest:
        calls = []

        def __init__(self, profile):
            self.profile = profile

        def call(self, method, path, *, json_body=None, params=None, multipart=None, timeout=None):
            from denodo_cli.transports.base import HttpResult
            HttpStepTest.FakeRest.calls.append((method, path, params, json_body))
            if method == "POST" and path == "/public/api/tags":
                return HttpResult(status=200, body={"id": 4242, "name": "verify_pii"})
            return HttpResult(status=200, body={"count": 0, "elements": []})

    def setUp(self):
        FakeVql.instances.clear()
        HttpStepTest.FakeRest.calls.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "skills" / "marketplace").mkdir(parents=True)
        (self.root / "skills" / "marketplace" / "SKILL.md").write_text(
            "### Tag\n\n```bash\n" + BASH_BLOCK + "```\n", encoding="utf-8")
        self.manifest = self.root / "chain.toml"
        self.manifest.write_text("""
[values]
database = "denodo_skills_test"
server_id = "306"
[[step]]
id = "mp-tag"
kind = "template"
channel = "http"
address = "skills/marketplace/SKILL.md#Tag"
marketplace = true
calls = [0, 1]
capture = { tag_id = "id" }
substitute = { "\\"pii\\"" = "\\"verify_pii\\"" }
""", encoding="utf-8")
        self.chain = load_chain(self.manifest)

    def test_marketplace_step_runs_only_the_listed_calls_and_captures(self):
        doc, code = run_chain(profile(marketplace_url="http://x/y"), self.chain, root=self.root,
                              vql_factory=FakeVql, rest_factory=HttpStepTest.FakeRest,
                              with_marketplace=True)
        self.assertEqual(code, 0, doc)
        self.assertEqual(len(HttpStepTest.FakeRest.calls), 2)
        self.assertEqual(doc["values"]["tag_id"], "4242")

    def test_a_non_2xx_answer_fails_the_step(self):
        class Failing(HttpStepTest.FakeRest):
            def call(self, method, path, **kw):
                from denodo_cli.transports.base import HttpResult
                return HttpResult(status=409, body=None)

        doc, code = run_chain(profile(marketplace_url="http://x/y"), self.chain, root=self.root,
                              vql_factory=FakeVql, rest_factory=Failing, with_marketplace=True)
        self.assertEqual(code, 1)
        self.assertFalse(doc["steps"][0]["ok"])
        self.assertEqual(doc["steps"][0]["error"]["status"], 409)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=scripts python3 -m unittest tests.test_commands_verify.ParseApiCallsTest -v`
Expected: FAIL — `ImportError: cannot import name 'parse_api_calls'`

- [ ] **Step 3: Write minimal implementation**

```python
# добавить в scripts/denodo_cli/commands/verify.py
import json
import shlex

from .api import api_call


def parse_api_calls(body: str) -> list[dict]:
    """``api <method> <path> [--param k=v] [--json '<text>']`` lines of a bash template."""
    joined = re.sub(r"\\\s*\n\s*", " ", body)
    calls: list[dict] = []
    for line in joined.splitlines():
        stripped = line.strip()
        if not stripped.startswith("api "):
            continue
        tokens = shlex.split(stripped)[1:]
        method, path = tokens[0].upper(), None
        params: dict[str, str] = {}
        body_text: str | None = None
        index = 1
        while index < len(tokens):
            token = tokens[index]
            if token == "--param":
                key, _, value = tokens[index + 1].partition("=")
                params[key] = value
                index += 2
            elif token == "--json":
                body_text = tokens[index + 1]
                index += 2
            elif token == "--env":
                index += 2
            elif token.startswith("-"):
                index += 2
            else:
                path = token
                index += 1
        calls.append({"method": method, "path": path, "params": params,
                      "json": json.loads(body_text) if body_text else None})
    return calls
```

Исполнение HTTP-шага в `_run_step` (ветка `step.channel == "http"`): взять тело блока, применить `render`, разобрать `parse_api_calls`, оставить вызовы из `step.calls` (пустой список — все), для каждого вызвать `api_call(profile, method, path, transport_factory=rest_factory, json_body=..., params=..., allow_destructive=True)`; неуспешный `code` — ошибка шага с `{"kind": "http", "status": …, "body": …}`; после последнего вызова записать в `values` захваченные ключи `capture` (значение берётся из тела ответа по имени поля верхнего уровня, приводится к `str`). Значения `values` попадают в отчёт полем `values` — так уборка и следующий шаг видят захваченные идентификаторы.

Уборка HTTP: в `[cleanup]` добавить `http = [{ method = "delete", path = "/public/api/tags/{tag_id}", params = { serverId = "{server_id}" } }]`; выполняется после VQL-уборки и только если соответствующие значения захвачены; пропущенная из-за отсутствия значения строка отмечается в отчёте `{"skipped": true}`.

- [ ] **Step 4: Extend the manifest**

Добавить в `verification/chain.toml` шаги маркетплейса: синхронизация каталога (`skills/marketplace/SKILL.md#Synchronising the marketplace catalog with VDP`, `marketplace = true`), тег (`#Tag, with an assignment`, `calls = [0, 1]`, `capture = { tag_id = "id" }`, подстановка имени на `{tag_prefix}pii`), категория (`#Category tree`, `calls = [0]`, `capture = { category_id = "id" }`). `serverId` берётся из `values.server_id`, значение по умолчанию — пустая строка, и тогда шаг падает с понятной ошибкой; на стенде `lab` его надо указать (`306`) либо задать `marketplace_server_id` в профиле.

Внешний элемент в цепочку **не входит**: его шаг требует применить VQL, полученный из ответа маркетплейса (`vql-metadata`), то есть новый вид шага «ответ одного канала — тело другого». Это отдельная задача; пометки `external-elements.md` остаются с T8d.

- [ ] **Step 5: Run the marketplace tail against the stand**

Run:
```bash
PYTHONPATH=scripts uv run --with denodo-sqlalchemy --with psycopg2-binary \
  scripts/denodo verify --env lab --with-marketplace --keep
```
Expected: `"ok": true`; в `values` видны `tag_id` и `category_id`. Затем прогон без `--keep` и проверка, что тег и категория удалены:
```bash
scripts/denodo api get --env lab /public/api/tag-management/tags --param serverId=306 --param nameFilter=verify_
```

- [ ] **Step 6: Add the integration case**

```python
# добавить в tests/integration/test_verify_chain.py
    @unittest.skipUnless(os.environ.get("DENODO_TEST_MARKETPLACE"), "DENODO_TEST_MARKETPLACE not set")
    def test_marketplace_tail_runs_and_cleans_up(self):
        from denodo_cli.transports import get_rest_transport

        doc, code = run_chain(self.profile, self.chain, root=REPO,
                              vql_factory=get_vql_transport(self.profile.transport),
                              rest_factory=get_rest_transport(), with_marketplace=True)
        self.assertEqual(code, 0, [s for s in doc["steps"] if not s["ok"]])
        self.assertTrue(all(not s["skipped"] for s in doc["steps"]))
        self.assertTrue(doc["cleanup"]["ran"])
```

- [ ] **Step 7: Commit**

```bash
git add scripts/denodo_cli/commands/verify.py verification/chain.toml tests/
git commit -m "feat(verify): хвост маркетплейса под флагом, с захватом id и уборкой"
```

---

### Task 10: Документация и закрытие задачи

**Files:**
- Modify: `docs/TASKS.md`, `docs/superpowers/specs/2026-09-04-denodo-skills-design.md`, `skills/execute/SKILL.md`, `CLAUDE.md`

- [ ] **Step 1: Уточнить спеку под то, что получилось**

В разделе 11.1 в абзаце «Что считается успехом» дописать, что `check` бывает двух видов: `expect = "rows"` (по умолчанию) и `expect = "no rows"` — последнее для проверок вида «сломанного нет» (`GET_VIEWS(… invalid only)` обязан быть пустым).

- [ ] **Step 2: Строка про команду в навыке `execute`**

В `skills/execute/SKILL.md` в перечень команд добавить: `verify` — runs the chain of templates from `verification/chain.toml` in its own test database and drops it afterwards; `--with-marketplace` adds the REST tail, `--keep` leaves the objects for inspection, `--update-marks` rewrites the `verified:` lines that passed.

- [ ] **Step 3: Обновить `CLAUDE.md`**

В абзац про слой исполнения дописать: прогон верификации — `PYTHONPATH=scripts uv run --with denodo-sqlalchemy --with psycopg2-binary scripts/denodo verify --env lab`.

- [ ] **Step 4: Закрыть T12 в трекере**

Перенести T12 из «Дальше» в «Сделано» с разделом, отвечающим на вопросы: что прогоняется (цепочка v1), что осталось непокрытым (внешний элемент маркетплейса — нужен шаг «ответ одного канала — тело другого»; шаблоны JDBC и JSON в цепочку не входят, их пометки остаются с T8b), и что T13 теперь опирается на `verify` как на готовый прогон.

- [ ] **Step 5: Run the whole suite one last time**

Run:
```bash
PYTHONPATH=scripts python3 -m unittest discover -s tests -t . -q
DENODO_TEST_ENV=lab PYTHONPATH=scripts uv run --with denodo-sqlalchemy --with psycopg2-binary \
  python -m unittest tests.integration -v
```
Expected: обе команды OK.

- [ ] **Step 6: Commit**

```bash
git add docs/ skills/execute/SKILL.md CLAUDE.md
git commit -m "docs(verify): команда описана в навыке execute, T12 закрыта в трекере"
```
