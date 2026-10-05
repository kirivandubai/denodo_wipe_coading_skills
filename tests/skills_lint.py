"""A lint of what a plugin user and the agent read: skills, README, CONTRIBUTING, manifests,
the CLI and the eval cases.

The review of all skills (2026-10-05) found most of its problems by hand, and they were
mechanical: Cyrillic, names of the server the skills were written against, descriptions
over the limit, templates without a verification mark or with a mark in another wording,
links and skill names that do not resolve, internal scope words. Each check here finds one
kind of them. A check takes the repository root and returns findings as
``path:line: message``; an empty list is a pass. ``test_skills_lint.py`` runs every check
over the repository (that is what CI fails on) and over small synthetic trees.

Print every finding of a tree, for instance of an older commit unpacked somewhere:

    PYTHONPATH=scripts python3 -m tests.skills_lint [root]

The lists below — blocks that are not templates, long files, long descriptions — are
explicit on purpose: adding to one is a line in the diff a reviewer sees.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

DESCRIPTION_LIMIT = 1024   # the Agent Skills limit on a skill's description
DESCRIPTION_BUDGET = 900   # CONTRIBUTING.md: what is left is room for the next trigger phrase
SKILL_LINES_LIMIT = 500    # a SKILL.md is read whole; the detail belongs in references/

# Descriptions over the budget, with their length in characters. One may shrink, never grow;
# when it shrinks the number here goes down with it, and back within the budget it leaves.
OVER_BUDGET: dict[str, int] = {}

# SKILL.md files over the limit, with their length in lines — the same ratchet.
LONG_SKILLS: dict[str, int] = {"datasources": 697, "marketplace": 562, "views": 722}

# Fenced blocks in skills/ that are not templates and so carry no verification mark:
# grammar, diagrams, what a server or a tool prints, a report the agent writes, a command
# line for the human. Keyed by file; each entry is a fragment of the block's text and why it
# is not a template. An entry that matches no unmarked block is reported, so the list
# cannot keep a block that has since become a template.
GRAMMAR = "grammar, not a statement to run"
SHAPE = "the shape of a message the agent writes to the human"
HUMAN_COMMAND = "a command the human types; the CLI's unit tests cover it"
LAUNCHER = "the Testing Tool's own launcher line, for the human"
UNMARKED_BLOCKS: dict[str, list[tuple[str, str]]] = {
    "skills/ai/SKILL.md": [("sales_analytics.product_review: 2,400 reviews", SHAPE)],
    "skills/ai/references/vectors.md": [
        ("embedding:vector<float,<dimension>>", "a column as DESC VQL prints it"),
    ],
    "skills/cache/SKILL.md": [("View sales_analytics.iv_household_income — read by", SHAPE)],
    "skills/datasources/references/base-view.md": [
        ("CREATE [ OR REPLACE ] TABLE [<database>.]<name> I18N <map>", GRAMMAR),
        ("blob boolean date decimal double", "a list of the type names"),
    ],
    "skills/datasources/references/df.md": [
        ("CREATE [ OR REPLACE ] DATASOURCE DF <name>", GRAMMAR),
        ("CREATE [ OR REPLACE ] WRAPPER DF <name>", GRAMMAR),
    ],
    "skills/datasources/references/jdbc.md": [
        ("CREATE [ OR REPLACE ] DATASOURCE JDBC <name>", GRAMMAR),
        ("amazon-athena-1.0 amazon-athena-3.0", "a list of the adapter names"),
    ],
    "skills/datasources/references/json.md": [("CREATE [ OR REPLACE ] WRAPPER JSON <name>", GRAMMAR)],
    "skills/dml/SKILL.md": [("sales_analytics.bv_orders_db_orders (orders table", SHAPE)],
    "skills/dml/references/statements.md": [
        ("INSERT INTO <view> ( <field> [, <field> ]* )", GRAMMAR),
        ("UPDATE <view> SET <field> = <value or expression>", GRAMMAR),
        ("DELETE FROM <view> [ WHERE <condition> ];", GRAMMAR),
    ],
    "skills/dml/references/writable-views.md": [
        ("[ WITH [ CASCADED | LOCAL ] CHECK OPTION ]", GRAMMAR),
        ("SOURCECONFIGURATION ( ALLOWDELETE = false )", GRAMMAR),
    ],
    "skills/execute/SKILL.md": [
        ("! ${CLAUDE_PLUGIN_ROOT}/scripts/denodo env init", HUMAN_COMMAND),
        ("! ${CLAUDE_PLUGIN_ROOT}/scripts/denodo secret encrypt", HUMAN_COMMAND),
    ],
    "skills/materialize/SKILL.md": [("Created dwh.reporting.household_income (ds_dwh)", SHAPE)],
    "skills/materialize/references/remote-tables.md": [
        ("CREATE [ OR REPLACE ] REMOTE TABLE <name>", GRAMMAR),
        ("REFRESH <base view made by CREATE_REMOTE_TABLE | summary>", GRAMMAR),
        ("DROP_REMOTE_TABLE( base_view_database_name : text", GRAMMAR),
        ("CREATE [ OR REPLACE ] MATERIALIZED TABLE [<db>.]<name>", GRAMMAR),
    ],
    "skills/materialize/references/summaries.md": [
        ("CREATE [ OR REPLACE ] SUMMARY VIEW <name>", GRAMMAR),
        ("ALTER SUMMARY VIEW <name>", GRAMMAR),
    ],
    "skills/metrics/references/metric-views.md": [("CREATE [ OR REPLACE ] METRIC VIEW <name>", GRAMMAR)],
    "skills/scheduler/SKILL.md": [
        ('"name": "iv_household_income_cache"', "the job file the marked calls below send"),
        ('"name": "household_income_by_band_csv"', "the job file the marked calls below send"),
        ("Job iv_household_income_cache, project sales_analytics", SHAPE),
    ],
    "skills/security/SKILL.md": [("Database sales_analytics. Readers today (CATALOG_PERMISSIONS)", SHAPE)],
    "skills/semantics/SKILL.md": [("Database claims_analytics — 12 views audited.", SHAPE)],
    "skills/testing/SKILL.md": [
        ("denodo/sales_analytics/\n  00_database.vql", "a folder layout"),
        ("scripts/denodo testing run --env dev", "a command of the plugin's CLI; its unit tests cover it"),
        ("bash denodo-test.sh file:", LAUNCHER),
    ],
    "skills/testing/references/format.md": [
        ("%RESULTS[exception] not found", GRAMMAR),
        ("bash denodo-test.sh file:", LAUNCHER),
        ("maxRowsInMemoryForMatching=10000", "the configuration file `testing config` writes"),
    ],
    "skills/views/SKILL.md": [("ENDPOINT <role name>  <view>  [PRINCIPAL]  (<multiplicity>)", GRAMMAR)],
    "skills/views/references/associations.md": [("DROP ASSOCIATION [ IF EXISTS ] <name>", GRAMMAR)],
    "skills/vql/SKILL.md": [("intent in words\n  → read .denodo/conventions.md", "a diagram of the loop")],
    "skills/vql/references/dialect.md": [
        ("vql run --env dev -e \"SELECT SUBSTR('abcdef', 1, 3) AS want_abc",
         "a probe through the CLI; the mark at the top of the file covers its expressions"),
    ],
}

# ---------------------------------------------------------------------------------------
# Which files are read by whom.


def _skill_docs(root: Path) -> list[Path]:
    return sorted((root / "skills").rglob("*.md"))


def _eval_cases(root: Path) -> list[Path]:
    """Files of the eval cases — prompts and graders — not the suite's own README or results."""
    evals = root / "evals"
    if not evals.is_dir():
        return []
    return sorted(path for path in evals.rglob("*")
                  if path.is_file() and path.parent != evals
                  and path.relative_to(evals).parts[0] != "results")


def _docs(root: Path) -> list[Path]:
    """Text a plugin user or the agent reads."""
    top = [root / name for name in ("README.md", "CONTRIBUTING.md")]
    manifests = sorted((root / ".claude-plugin").glob("*.json"))
    return _skill_docs(root) + [path for path in top if path.is_file()] + manifests + _eval_cases(root)


def _cli(root: Path) -> list[Path]:
    """The CLI's source: its help text and messages are what a user of the tool reads."""
    scripts = root / "scripts"
    if not scripts.is_dir():
        return []
    launcher = [scripts / "denodo"] if (scripts / "denodo").is_file() else []
    return launcher + sorted(path for path in scripts.rglob("*.py") if "__pycache__" not in path.parts)


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------------------------------
# Markdown, as far as the checks need it: fenced blocks, and paragraphs between them.

FENCE = re.compile(r"^(\s*)```(\S*)\s*$")
HEADING = re.compile(r"^#{1,6}\s")
CODE_SPAN = re.compile(r"(`+).+?\1")


@dataclass
class Block:
    start: int                       # 1-based line of the opening fence
    lines: list[str]                 # the body, fences excluded


@dataclass
class Paragraph:
    """Consecutive non-blank lines outside a block, joined — a mark or a phrase may wrap."""
    start: int
    heading: bool = False
    text: str = ""
    offsets: list[int] = field(default_factory=list)   # where each line begins in ``text``

    def add(self, line: str) -> None:
        if self.text:
            self.text += " "
        self.offsets.append(len(self.text))
        self.text += line.strip()

    def line_at(self, offset: int) -> int:
        index = 0
        for number, begins in enumerate(self.offsets):
            if begins <= offset:
                index = number
        return self.start + index

    def prose(self) -> str:
        """The text with inline code blanked out, offsets kept: code is quoted, not said."""
        return CODE_SPAN.sub(lambda match: " " * len(match.group(0)), self.text)


def _parse(lines: list[str]) -> list[Block | Paragraph]:
    elements: list[Block | Paragraph] = []
    block: Block | None = None
    paragraph: Paragraph | None = None
    for number, line in enumerate(lines, start=1):
        if block is not None:
            if line.lstrip().startswith("```"):    # a closing fence may sit at any indent
                block = None
            else:
                block.lines.append(line)
            continue
        if FENCE.match(line):
            paragraph = None
            block = Block(start=number, lines=[])
            elements.append(block)
        elif not line.strip():
            paragraph = None
        elif HEADING.match(line):
            heading = Paragraph(start=number, heading=True)
            heading.add(line)
            elements.append(heading)
            paragraph = None
        else:
            if paragraph is None:
                paragraph = Paragraph(start=number)
                elements.append(paragraph)
            paragraph.add(line)
    return elements


# ---------------------------------------------------------------------------------------
# 1. Language: the plugin is in English.

CYRILLIC = re.compile(r"[\u0400-\u04FF]")


def check_language(root: Path) -> list[str]:
    findings = []
    for path in _docs(root) + _cli(root):
        for number, line in enumerate(_lines(path), start=1):
            if CYRILLIC.search(line):
                findings.append(f"{_rel(root, path)}:{number}: Cyrillic — the plugin is in English")
    return findings


# ---------------------------------------------------------------------------------------
# 2. Names of one installation: the server the skills were written against, its datasets
# and the prefixes of test runs. TPC-DS names are a public benchmark and stay.

INSTALLATION_NAMES = [
    (re.compile(r"\b(?:pii_data|business_views)\b"), "a tag of the test server"),
    (re.compile(r"\b(?:XEPDB1|RETAIL|FINANCIAL_SERVICES)\b"), "the test server's Oracle service or schema"),
    (re.compile(r"\b(?:sspm_sources|denodo_demolets|denodo_asset_extensions|denodo_dashboard"
                r"|enterprise_data|(?i:verticals))\b"), "a database of the test server"),
    (re.compile(r"\b(?:oracle|sql-server|postgres-pgvector|denodo-platform)-demo\b"), "a host of the test server"),
    (re.compile(r"Demo Standard Default"), "the test server's VDP server in the marketplace"),
    (re.compile(r"\b(?:29996|29999|29090|29443)\b"), "a port of the test server"),
    (re.compile(r"--env[ =]lab\b"), "the test server's profile"),
    (re.compile(r"(?i)\b(?:green\d+_|zq\d*_)"), "the prefix of a test run"),
]

# Words of the project's process: legitimate in the CLI's code comments, not in the text.
PROCESS_WORDS = [
    (re.compile(r"\bverify_\w+"), "a name of the verification chain outside the chain"),
    (re.compile(r"\bT\d{1,2}\b"), "a task id of the project"),
]


def check_installation_names(root: Path) -> list[str]:
    findings = []
    docs = set(_docs(root))
    for path in _docs(root) + _cli(root):
        patterns = INSTALLATION_NAMES + (PROCESS_WORDS if path in docs else [])
        for number, line in enumerate(_lines(path), start=1):
            for pattern, what in patterns:
                for match in pattern.finditer(line):
                    findings.append(f"{_rel(root, path)}:{number}: `{match.group(0)}` — {what}")
    return findings


# ---------------------------------------------------------------------------------------
# 3. Scope words: "v1" is the project's planning language, not something a user can act on.

SCOPE_WORDS = re.compile(r"(?i)\bv1\b")


def check_scope_words(root: Path) -> list[str]:
    findings = []
    for path in _docs(root):
        for element in _parse(_lines(path)):
            if isinstance(element, Paragraph):
                for match in SCOPE_WORDS.finditer(element.prose()):
                    findings.append(f"{_rel(root, path)}:{element.line_at(match.start())}: "
                                    f"`{match.group(0)}` — the project's scope, not the user's")
    return findings


# ---------------------------------------------------------------------------------------
# 4. Frontmatter: the name, and the description the skill is chosen by.

FRONTMATTER_KEY = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*?)\s*$")


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1].replace('\\"', '"')
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _frontmatter(lines: list[str]) -> dict[str, tuple[int, str]] | None:
    """Top-level keys of a YAML frontmatter, each with its line and its value as one string.

    Enough YAML for a skill's header: plain and quoted scalars, plain scalars continued on
    indented lines, and ``>`` / ``|`` block scalars.
    """
    if not lines or lines[0].strip() != "---":
        return None
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None
    fields: dict[str, tuple[int, str]] = {}
    key, line_of_key, literal, parts = None, 0, False, []

    def flush() -> None:
        if key is not None:
            fields[key] = (line_of_key, ("\n" if literal else " ").join(part for part in parts if part))

    for number, line in enumerate(lines[1:end], start=2):
        match = FRONTMATTER_KEY.match(line)
        if match and not line[:1].isspace():
            flush()
            key, line_of_key, value = match.group(1), number, match.group(2)
            literal = value.startswith("|")
            parts = [] if value[:1] in (">", "|") else [_unquote(value)]
        elif key is not None:
            parts.append(line.strip())
    flush()
    return fields


def _ratchet(name: str, value: int, limit: int, listed: dict[str, int], table: str, unit: str,
            bound: str = "limit") -> str | None:
    """A value over its limit may stay only listed, at exactly its current size."""
    recorded = listed.get(name)
    if recorded is None:
        if value > limit:
            return (f"{value} {unit}, over the {bound} of {limit} — shorten it, or list "
                    f"{name!r}: {value} in {table} for a reviewer to see")
        return None
    if value <= limit:
        return f"{value} {unit}, within the {bound} of {limit} now — remove {name!r} from {table}"
    if value > recorded:
        return f"grew to {value} {unit}; {table} allows {recorded} — it may shrink, never grow"
    if value < recorded:
        return f"shrank to {value} {unit} — lower {table}[{name!r}] from {recorded} to {value}"
    return None


def check_frontmatter(root: Path, over_budget: dict[str, int] | None = None) -> list[str]:
    over_budget = OVER_BUDGET if over_budget is None else over_budget
    findings = []
    skills = root / "skills"
    directories = sorted(path for path in skills.iterdir() if path.is_dir()) if skills.is_dir() else []
    for directory in directories:
        name = directory.name
        path = directory / "SKILL.md"
        where = _rel(root, path)
        if name.startswith("denodo-"):
            findings.append(f"{where}:1: directory {name!r} — the plugin adds `denodo:` itself, "
                            f"so it would be invoked as /denodo:{name}")
        if not path.is_file():
            findings.append(f"{where}:1: missing — a skill directory without its SKILL.md")
            continue
        fields = _frontmatter(_lines(path))
        if fields is None:
            findings.append(f"{where}:1: no frontmatter between `---` lines")
            continue
        declared = fields.get("name", (1, ""))
        if declared[1] != name:
            findings.append(f"{where}:{declared[0]}: name {declared[1]!r} differs from the directory {name!r}")
        if "description" not in fields or not fields["description"][1]:
            findings.append(f"{where}:1: no description — the skill cannot be chosen")
            continue
        line, description = fields["description"]
        length = len(description)
        if length > DESCRIPTION_LIMIT:
            findings.append(f"{where}:{line}: description is {length} characters, over the Agent "
                            f"Skills limit of {DESCRIPTION_LIMIT}")
        problem = _ratchet(name, length, DESCRIPTION_BUDGET, over_budget, "OVER_BUDGET", "characters",
                           bound="budget")
        if problem:
            findings.append(f"{where}:{line}: description: {problem} (the budget: CONTRIBUTING.md)")
    names = {directory.name for directory in directories}
    findings += [f"tests/skills_lint.py:1: OVER_BUDGET lists {name!r}, which is not a skill"
                 for name in sorted(set(over_budget) - names)]
    return findings


# ---------------------------------------------------------------------------------------
# 5. Verification marks: every template carries one, and only in the two canonical forms.

MARK_WORD = re.compile(r"(?<![\w`])(?:un)?verified:")
CANONICAL_MARK = re.compile(r"verified:\s+9\.5(?:\.\d+)?\s+\(live,\s+(?P<date>\d{4}-\d{2}-\d{2})\)"
                            r"|unverified:\s+9\.5\s+documentation\s+only\b")
LIVE_LABEL = re.compile(r"\(live(?:,\s*\d{4}-\d{2}-\d{2})?\)")
BEFORE_LIVE_LABEL = re.compile(r"verified:\s+9\.5(?:\.\d+)?\s+$")
CANONICAL_FORMS = "`verified: 9.5.x (live, YYYY-MM-DD)` or `unverified: 9.5 documentation only`"


def _mark_problems(text: str) -> list[tuple[int, str]]:
    """Offsets in ``text`` of marks that are not canonical, with what is wrong."""
    problems = []
    for match in MARK_WORD.finditer(text):
        canonical = CANONICAL_MARK.match(text, match.start())
        if not canonical:
            seen = " ".join(text[match.start():match.start() + 48].split())
            problems.append((match.start(), f"mark `{seen}…` is not canonical — {CANONICAL_FORMS}"))
            continue
        if canonical.group("date"):
            try:
                dt.date.fromisoformat(canonical.group("date"))
            except ValueError:
                problems.append((match.start(), f"mark date {canonical.group('date')} is not a date"))
    for match in LIVE_LABEL.finditer(text):
        if not BEFORE_LIVE_LABEL.search(text[max(0, match.start() - 32):match.start()]):
            problems.append((match.start(), f"`{match.group(0)}` outside a mark — {CANONICAL_FORMS}"))
    return problems


def _has_mark(element: Block | Paragraph | None) -> bool:
    """A block's own mark, or a paragraph's. A neighbouring block's mark covers only it."""
    if isinstance(element, Block):
        return any(MARK_WORD.search(line) for line in element.lines)
    if isinstance(element, Paragraph) and not element.heading:
        return bool(MARK_WORD.search(element.prose()))
    return False


def check_marks(root: Path, unmarked: dict[str, list[tuple[str, str]]] | None = None) -> list[str]:
    unmarked = UNMARKED_BLOCKS if unmarked is None else unmarked
    findings = []
    used: set[tuple[str, str]] = set()
    for path in _skill_docs(root):
        where = _rel(root, path)
        elements = _parse(_lines(path))
        for index, element in enumerate(elements):
            if isinstance(element, Paragraph):
                for offset, problem in _mark_problems(element.prose()):
                    findings.append(f"{where}:{element.line_at(offset)}: {problem}")
                continue
            for number, line in enumerate(element.lines, start=element.start + 1):
                findings += [f"{where}:{number}: {problem}" for _, problem in _mark_problems(line)]
            neighbours = [elements[i] for i in (index - 1, index + 1)
                          if 0 <= i < len(elements) and isinstance(elements[i], Paragraph)]
            if _has_mark(element) or any(_has_mark(paragraph) for paragraph in neighbours):
                continue
            body = "\n".join(element.lines)
            allowed = [needle for needle, _ in unmarked.get(where, []) if needle in body]
            used.update((where, needle) for needle in allowed)
            if not allowed:
                first = next((line.strip() for line in element.lines if line.strip()), "")
                findings.append(f"{where}:{element.start}: block `{first[:60]}` has no mark — "
                                f"inside it, or in the paragraph right above or below; a block "
                                f"that is not a template goes into UNMARKED_BLOCKS")
    for where, entries in sorted(unmarked.items()):
        for needle, reason in entries:
            if (where, needle) not in used:
                findings.append(f"{where}:1: UNMARKED_BLOCKS entry {needle!r} ({reason}) matches no "
                                f"unmarked block — remove it, or the block needs its mark")
    return findings


# ---------------------------------------------------------------------------------------
# 6. Links: references/ files, skill names and relative links resolve.

REFERENCE = re.compile(r"(?<![\w./-])(?:(?:skills/)?(?P<skill>[a-z][\w-]*)/)?references/(?P<file>[\w.-]+\.md)")
SKILL_NAME = re.compile(r"(?<![\w:])/denodo:(?P<name>[a-z][\w-]*)")
GRADER_SKILL = re.compile(r"(?<![\w:/])/?denodo:(?P<name>[a-z][\w-]*)")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\((?P<target>[^)\s]+)\)")
# Names written after /denodo: that are not skills on purpose.
NOT_SKILLS = {"denodo-views"}   # CONTRIBUTING.md: what a `denodo-` prefixed directory would become


def _reference_problem(root: Path, own: str, text: str, match: re.Match) -> str | None:
    skills = root / "skills"
    if match.group("skill"):
        if (skills / match.group("skill") / "references" / match.group("file")).is_file():
            return None
        return f"`{match.group(0)}` does not exist"
    if (skills / own / "references" / match.group("file")).is_file():
        return None
    named = list(SKILL_NAME.finditer(text, 0, match.start()))
    if named and (skills / named[-1].group("name") / "references" / match.group("file")).is_file():
        return None
    other = f" nor in /denodo:{named[-1].group('name')}, named before it" if named else ""
    return f"`references/{match.group('file')}` is not in /denodo:{own}{other}"


def check_links(root: Path) -> list[str]:
    findings = []
    skills = root / "skills"
    names = {path.name for path in skills.iterdir() if path.is_dir()} if skills.is_dir() else set()
    for path in _skill_docs(root):
        where, own = _rel(root, path), path.relative_to(skills).parts[0]
        for element in _parse(_lines(path)):
            texts = ([(element.start + 1 + i, line, None) for i, line in enumerate(element.lines)]
                     if isinstance(element, Block) else [(element.start, element.text, element)])
            for start, text, paragraph in texts:
                for match in REFERENCE.finditer(text):
                    problem = _reference_problem(root, own, text, match)
                    if problem:
                        line = paragraph.line_at(match.start()) if paragraph else start
                        findings.append(f"{where}:{line}: {problem}")
    evals = set(_eval_cases(root))
    for path in _docs(root):
        where = _rel(root, path)
        for number, line in enumerate(_lines(path), start=1):
            pattern = GRADER_SKILL if path in evals else SKILL_NAME
            for match in pattern.finditer(line):
                if match.group("name") not in names | NOT_SKILLS:
                    findings.append(f"{where}:{number}: `{match.group(0)}` — no such skill")
            if path.suffix != ".md":
                continue
            for match in MARKDOWN_LINK.finditer(line):
                target = match.group("target")
                if re.match(r"[a-z][\w+.-]*:", target) or target.startswith("#"):
                    continue
                if not (path.parent / target.split("#")[0]).exists():
                    findings.append(f"{where}:{number}: link `{target}` does not resolve")
    return findings


# ---------------------------------------------------------------------------------------
# 7. Length of SKILL.md.


def check_skill_length(root: Path, ceilings: dict[str, int] | None = None) -> list[str]:
    ceilings = LONG_SKILLS if ceilings is None else ceilings
    findings = []
    skills = root / "skills"
    present = set()
    for path in sorted(skills.glob("*/SKILL.md")) if skills.is_dir() else []:
        name = path.parent.name
        present.add(name)
        problem = _ratchet(name, len(_lines(path)), SKILL_LINES_LIMIT, ceilings, "LONG_SKILLS", "lines")
        if problem:
            findings.append(f"{_rel(root, path)}:1: {problem}")
    findings += [f"tests/skills_lint.py:1: LONG_SKILLS lists {name!r}, which is not a skill"
                 for name in sorted(set(ceilings) - present)]
    return findings


CHECKS = (check_language, check_installation_names, check_scope_words, check_frontmatter,
          check_marks, check_links, check_skill_length)


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else REPO
    findings = [finding for check in CHECKS for finding in check(root)]
    print("\n".join(findings) if findings else "clean")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
