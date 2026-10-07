"""The lint of what a plugin user and the agent read — see ``tests/skills_lint.py``.

Two halves. ``TreeIsCleanTest`` runs every check over the repository itself: this is what
CI fails on. The other classes run each check over a few synthetic files, so that a check
which silently stopped firing — a regex that no longer matches anything — fails here
instead of passing the tree by finding nothing.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests import skills_lint as lint

REPO = Path(__file__).resolve().parents[1]

FRONTMATTER = "---\nname: {name}\ndescription: {description}\n---\n\n"


def skill(name: str, body: str = "# Skill\n", description: str = "Use when testing.") -> dict[str, str]:
    return {f"skills/{name}/SKILL.md": FRONTMATTER.format(name=name, description=description) + body}


class TreeTestCase(unittest.TestCase):
    """Writes ``files`` into a temporary repository root for one test."""

    def tree(self, files: dict[str, str]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for relative, text in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return root

    def assertFinds(self, findings: list[str], *fragments: str) -> None:
        joined = "\n".join(findings)
        for fragment in fragments:
            self.assertIn(fragment, joined, f"expected a finding with {fragment!r}, got:\n{joined}")

    def assertClean(self, findings: list[str]) -> None:
        self.assertEqual(findings, [], "\n".join(findings))


class TreeIsCleanTest(unittest.TestCase):
    """The repository passes every check. A failure lists every finding, one per line."""

    def _check(self, check) -> None:
        findings = check(REPO)
        self.assertEqual(findings, [], "\n" + "\n".join(findings))

    def test_language(self):
        self._check(lint.check_language)

    def test_installation_names(self):
        self._check(lint.check_installation_names)

    def test_scope_words(self):
        self._check(lint.check_scope_words)

    def test_frontmatter(self):
        self._check(lint.check_frontmatter)

    def test_marks(self):
        self._check(lint.check_marks)

    def test_links(self):
        self._check(lint.check_links)

    def test_skill_length(self):
        self._check(lint.check_skill_length)


class LanguageTest(TreeTestCase):
    def test_cyrillic_in_a_skill_is_found_with_its_line(self):
        root = self.tree({**skill("views", "# Views\n\nСоздать представление.\n")})
        self.assertFinds(lint.check_language(root), "skills/views/SKILL.md:8")

    def test_cyrillic_in_the_cli_is_found(self):
        root = self.tree({"scripts/denodo_cli/cli.py": 'HELP = "профиль"\n'})
        self.assertFinds(lint.check_language(root), "scripts/denodo_cli/cli.py:1")

    def test_cyrillic_in_an_eval_prompt_is_found(self):
        root = self.tree({"evals/routing-views/prompt.md": "Сделай витрину.\n"})
        self.assertFinds(lint.check_language(root), "evals/routing-views/prompt.md:1")

    def test_an_outcome_scenario_is_checked_and_its_byproducts_are_not(self):
        # evals/outcome holds scenario prompts the agent reads (checked) beside the runner's
        # compiled modules and results (never text a person wrote).
        root = self.tree({"evals/outcome/scenarios/mart/scenario.toml": 'prompt = "Сделай витрину."\n',
                          "evals/outcome/results/2026/report.json": '{"final": "Готово"}\n'})
        cache = root / "evals/outcome/__pycache__/run.cpython-314.pyc"
        cache.parent.mkdir(parents=True)
        cache.write_bytes(b"\x00\xb6\xff binary")
        findings = lint.check_language(root)
        self.assertFinds(findings, "evals/outcome/scenarios/mart/scenario.toml:1")
        self.assertNotIn("results", "\n".join(findings))

    def test_project_documents_are_not_checked(self):
        root = self.tree({"docs/TASKS.md": "Задачи.\n", "CLAUDE.md": "Инструкции.\n"})
        self.assertClean(lint.check_language(root))

    def test_the_eval_suites_readme_is_checked(self):
        # contributors are sent there to turn a misrouted session into a case
        root = self.tree({"evals/README.md": "Кейсы.\n"})
        self.assertFinds(lint.check_language(root), "evals/README.md:1")

    def test_other_non_ascii_sample_data_passes(self):
        root = self.tree({**skill("views", "# Views\n\n`straße`, `Tokyo 東京`, `domingo` — ∪\n")})
        self.assertClean(lint.check_language(root))


class InstallationNamesTest(TreeTestCase):
    def test_a_test_server_tag_is_found(self):
        root = self.tree({**skill("marketplace", "# M\n\nTag the view `pii_data`.\n")})
        self.assertFinds(lint.check_installation_names(root), "skills/marketplace/SKILL.md:8", "pii_data")

    def test_the_test_servers_oracle_is_found(self):
        root = self.tree({**skill("datasources",
                                  "# D\n\n```sql\nDATABASEURI = 'jdbc:oracle:thin:@//h:1521/XEPDB1'\n"
                                  "CATALOG = 'RETAIL'\n```\n")})
        self.assertFinds(lint.check_installation_names(root), "XEPDB1", "RETAIL")

    def test_retail_as_a_word_passes(self):
        root = self.tree({**skill("marketplace", '# M\n\n{"name":"Retail","description":"Retail marts"}\n')})
        self.assertClean(lint.check_installation_names(root))

    def test_a_demo_database_and_host_are_found(self):
        root = self.tree({**skill("views", "# V\n\nRead `sspm_sources.store` on `sql-server-demo:1433`.\n")})
        self.assertFinds(lint.check_installation_names(root), "sspm_sources", "sql-server-demo")

    def test_run_prefixes_are_found(self):
        root = self.tree({**skill("views", "# V\n\n`green3_store`, `zq38_probe`, `ZQ_X`.\n")})
        self.assertFinds(lint.check_installation_names(root), "green3_", "zq38_", "ZQ_")

    def test_a_verify_name_outside_the_chain_is_found(self):
        root = self.tree({**skill("security", "# S\n\n```sql\nCREATE ROLE verify_reader;\n```\n")})
        self.assertFinds(lint.check_installation_names(root), "verify_reader")

    def test_the_bare_verify_prefix_describing_the_chain_passes(self):
        root = self.tree({**skill("execute", "# E\n\nRemoves the server-level `verify_` tags.\n")})
        self.assertClean(lint.check_installation_names(root))

    def test_the_test_servers_profile_and_ports_are_found(self):
        root = self.tree({**skill("execute", "# E\n\n`vql run --env lab` on port 29996.\n")})
        self.assertFinds(lint.check_installation_names(root), "--env lab", "29996")

    def test_default_ports_pass(self):
        root = self.tree({**skill("execute", "# E\n\nThe port from the profile, 9996 by default; 9999, 9090.\n")})
        self.assertClean(lint.check_installation_names(root))

    def test_a_task_id_in_a_skill_is_found(self):
        root = self.tree({**skill("views", "# V\n\nAs measured in T21.\n")})
        self.assertFinds(lint.check_installation_names(root), "T21")

    def test_a_task_id_in_a_cli_comment_passes(self):
        root = self.tree({"scripts/denodo_cli/safety.py": "# Decided in T20.\n"})
        self.assertClean(lint.check_installation_names(root))

    def test_a_server_name_in_the_cli_is_found(self):
        root = self.tree({"scripts/denodo_cli/env.py": 'DEFAULT = "http://localhost:29090"\n'})
        self.assertFinds(lint.check_installation_names(root), "scripts/denodo_cli/env.py:1", "29090")


class ScopeWordsTest(TreeTestCase):
    def test_outside_v1_is_found(self):
        root = self.tree({**skill("views", "# V\n\nPrivileges are outside v1 — Design Studio.\n")})
        self.assertFinds(lint.check_scope_words(root), "skills/views/SKILL.md:8", "v1")

    def test_v1_wrapped_across_lines_is_found(self):
        root = self.tree({**skill("views", "# V\n\nThat is not in\nv1 yet.\n")})
        self.assertFinds(lint.check_scope_words(root), "skills/views/SKILL.md:9")

    def test_v1_as_a_name_in_code_passes(self):
        root = self.tree({**skill("procedures",
                                  "# P\n\n`RETURN ROW (out1, out2) VALUES (v1, v2);`\n\n"
                                  "```sql\nSELECT v1 FROM t;\n```\n")})
        self.assertClean(lint.check_scope_words(root))


class FrontmatterTest(TreeTestCase):
    def test_a_description_over_the_limit_is_found(self):
        root = self.tree({**skill("views", description="x" * 1025)})
        self.assertFinds(lint.check_frontmatter(root, over_budget={"views": 1025}),
                         "skills/views/SKILL.md", "1025", "1024")

    def test_a_description_over_the_budget_is_found(self):
        root = self.tree({**skill("views", description="x" * 901)})
        self.assertFinds(lint.check_frontmatter(root, over_budget={}), "901", "budget of 900")

    def test_a_listed_description_that_grew_is_found(self):
        root = self.tree({**skill("views", description="x" * 950)})
        self.assertFinds(lint.check_frontmatter(root, over_budget={"views": 940}), "950", "940")

    def test_a_listed_description_that_shrank_asks_for_the_lower_number(self):
        root = self.tree({**skill("views", description="x" * 930)})
        self.assertFinds(lint.check_frontmatter(root, over_budget={"views": 940}), "930")

    def test_a_listed_description_back_within_the_budget_asks_to_be_unlisted(self):
        root = self.tree({**skill("views", description="x" * 800)})
        self.assertFinds(lint.check_frontmatter(root, over_budget={"views": 940}), "views")

    def test_a_description_within_the_budget_passes(self):
        root = self.tree({**skill("views", description="x" * 900)})
        self.assertClean(lint.check_frontmatter(root, over_budget={}))

    def test_a_folded_description_is_measured_joined(self):
        text = "---\nname: views\ndescription: >\n  " + "x" * 600 + "\n  " + "y" * 600 + "\n---\n"
        root = self.tree({"skills/views/SKILL.md": text})
        self.assertFinds(lint.check_frontmatter(root, over_budget={}), "1201")

    def test_a_name_that_differs_from_the_directory_is_found(self):
        root = self.tree({"skills/views/SKILL.md": FRONTMATTER.format(name="view", description="d")})
        self.assertFinds(lint.check_frontmatter(root, over_budget={}), "skills/views/SKILL.md", "view")

    def test_a_missing_description_is_found(self):
        root = self.tree({"skills/views/SKILL.md": "---\nname: views\n---\n"})
        self.assertFinds(lint.check_frontmatter(root, over_budget={}), "description")

    def test_a_denodo_prefixed_directory_is_found(self):
        root = self.tree({**skill("denodo-views")})
        self.assertFinds(lint.check_frontmatter(root, over_budget={}), "denodo-views")


class MarksTest(TreeTestCase):
    def test_a_block_without_a_mark_is_found(self):
        root = self.tree({**skill("catalog", "# C\n\n## Database\n\n```sql\nCREATE DATABASE d;\n```\n")})
        self.assertFinds(lint.check_marks(root, unmarked={}), "skills/catalog/SKILL.md:10", "no mark")

    def test_a_mark_inside_the_block_passes(self):
        root = self.tree({**skill("catalog",
                                  "# C\n\n```sql\n-- verified: 9.5.1 (live, 2026-09-09)\nCREATE DATABASE d;\n```\n")})
        self.assertClean(lint.check_marks(root, unmarked={}))

    def test_a_mark_in_the_paragraph_above_passes(self):
        root = self.tree({**skill("semantics",
                                  "# S\n\nAll *verified: 9.5.1\n(live, 2026-09-30)*; each is marked.\n\n"
                                  "```sql\nALTER VIEW v DESCRIPTION = 'd';\n```\n")})
        self.assertClean(lint.check_marks(root, unmarked={}))

    def test_a_mark_in_the_paragraph_below_passes(self):
        root = self.tree({**skill("views",
                                  "# V\n\n```\nCREATE ASSOCIATION <name>\n```\n\n"
                                  "*verified: 9.5.1 (live, 2026-09-10)*, every clause.\n")})
        self.assertClean(lint.check_marks(root, unmarked={}))

    def test_a_mark_two_paragraphs_away_does_not_count(self):
        root = self.tree({**skill("views",
                                  "# V\n\n*verified: 9.5.1 (live, 2026-09-10)*\n\nAnother point.\n\n"
                                  "```sql\nCREATE VIEW v AS SELECT 1;\n```\n\nAnd more.\n")})
        self.assertFinds(lint.check_marks(root, unmarked={}), "no mark")

    def test_an_allowlisted_block_passes(self):
        root = self.tree({**skill("views", "# V\n\n```\nCREATE [ OR REPLACE ] VIEW <name>\n```\n")})
        self.assertClean(lint.check_marks(
            root, unmarked={"skills/views/SKILL.md": [("CREATE [ OR REPLACE ] VIEW <name>", "grammar")]}))

    def test_an_allowlist_entry_matching_no_block_is_found(self):
        root = self.tree({**skill("views", "# V\n")})
        self.assertFinds(lint.check_marks(
            root, unmarked={"skills/views/SKILL.md": [("CREATE [ OR REPLACE ] VIEW <name>", "grammar")]}),
            "CREATE [ OR REPLACE ] VIEW <name>")

    def test_an_allowlist_entry_for_a_marked_block_is_found(self):
        root = self.tree({**skill("views",
                                  "# V\n\n```sql\n-- verified: 9.5.1 (live, 2026-09-10)\nCREATE VIEW v AS SELECT 1;\n```\n")})
        self.assertFinds(lint.check_marks(
            root, unmarked={"skills/views/SKILL.md": [("CREATE VIEW v", "grammar")]}), "CREATE VIEW v")

    def test_a_mark_without_a_date_is_found(self):
        root = self.tree({**skill("execute", "# E\n\nEvery one of them *verified: 9.5.1 (live)*:\n")})
        self.assertFinds(lint.check_marks(root, unmarked={}), "skills/execute/SKILL.md:8", "not canonical")

    def test_an_unverified_mark_in_another_wording_is_found(self):
        root = self.tree({**skill("marketplace", "# M\n\n```bash\n# unverified: 9.5 OpenAPI only\ncall\n```\n")})
        self.assertFinds(lint.check_marks(root, unmarked={}), "skills/marketplace/SKILL.md:9", "not canonical")

    def test_a_live_date_without_the_mark_word_is_found(self):
        root = self.tree({**skill("marketplace", "# M\n\nBoth verified on 9.5.1 (live, 2026-09-10):\n")})
        self.assertFinds(lint.check_marks(root, unmarked={}), "skills/marketplace/SKILL.md:8")

    def test_a_live_label_without_a_date_is_found(self):
        root = self.tree({**skill("cache", "# C\n\nIt breaks on every full reload *(live)*:\n")})
        self.assertFinds(lint.check_marks(root, unmarked={}), "skills/cache/SKILL.md:8", "(live)")

    def test_a_mark_in_the_block_right_after_does_not_count(self):
        # A chain is marked as a whole inside one block. A body in a block of its own that a
        # later call sends is listed in UNMARKED_BLOCKS, saying which mark covers it.
        root = self.tree({**skill("scheduler",
                                  "# S\n\nThe job file — the mark of the calls below covers it:\n\n"
                                  "```json\n{\"name\": \"job\"}\n```\n\n"
                                  "```bash\n# verified: 9.5.1 (live, 2026-10-05)\ncall\n```\n")})
        self.assertFinds(lint.check_marks(root, unmarked={}), "skills/scheduler/SKILL.md:10", "no mark")

    def test_an_impossible_date_is_found(self):
        root = self.tree({**skill("views", "# V\n\nA fact — *verified: 9.5.1 (live, 2026-13-01)*.\n")})
        self.assertFinds(lint.check_marks(root, unmarked={}), "2026-13-01")

    def test_a_mark_for_another_version_is_found(self):
        root = self.tree({**skill("views", "# V\n\nA fact — *verified: 8.0 (live, 2026-09-01)*.\n")})
        self.assertFinds(lint.check_marks(root, unmarked={}), "not canonical")

    def test_both_canonical_forms_and_mentions_in_code_pass(self):
        root = self.tree({**skill("views",
                                  "# V\n\nFacts marked `verified:` were run; the `# verified:` line;\n"
                                  "a fact — *unverified: 9.5 documentation only*; another —\n"
                                  "*verified: 9.5.1 (live, 2026-09-10)*. Write `verified: 9.5.1 (live, <date>)`.\n")})
        self.assertClean(lint.check_marks(root, unmarked={}))

    def test_readme_blocks_are_not_templates(self):
        root = self.tree({"README.md": "# R\n\n```\nclaude plugin install denodo\n```\n"})
        self.assertClean(lint.check_marks(root, unmarked={}))


class LinksTest(TreeTestCase):
    def test_a_reference_that_does_not_exist_is_found(self):
        root = self.tree({**skill("views", "# V\n\nSee `references/missing.md`.\n")})
        self.assertFinds(lint.check_links(root), "skills/views/SKILL.md:8", "references/missing.md")

    def test_a_reference_of_the_skill_itself_passes(self):
        root = self.tree({**skill("views", "# V\n\nSee `references/arrays.md`.\n"),
                          "skills/views/references/arrays.md": "# Arrays\n"})
        self.assertClean(lint.check_links(root))

    def test_a_reference_from_inside_references_resolves_in_the_same_skill(self):
        root = self.tree({**skill("views"),
                          "skills/views/references/derived.md": "See `references/arrays.md`.\n",
                          "skills/views/references/arrays.md": "# Arrays\n"})
        self.assertClean(lint.check_links(root))

    def test_a_reference_of_the_skill_named_before_it_passes(self):
        root = self.tree({**skill("datasources", "# D\n\nArrays are `/denodo:views`\n(`references/arrays.md`).\n"),
                          **skill("views"),
                          "skills/views/references/arrays.md": "# Arrays\n"})
        self.assertClean(lint.check_links(root))

    def test_a_reference_of_another_skill_without_its_name_is_found(self):
        root = self.tree({**skill("datasources", "# D\n\nSee `references/arrays.md`.\n"),
                          **skill("views"),
                          "skills/views/references/arrays.md": "# Arrays\n"})
        self.assertFinds(lint.check_links(root), "skills/datasources/SKILL.md:8")

    def test_a_skill_name_that_does_not_exist_is_found(self):
        root = self.tree({**skill("views", "# V\n\nThat is `/denodo:deploy`.\n")})
        self.assertFinds(lint.check_links(root), "skills/views/SKILL.md:8", "/denodo:deploy")

    def test_a_relative_link_that_does_not_resolve_is_found(self):
        root = self.tree({"README.md": "See [the cases](evals/README.md) and [license](LICENSE).\n",
                          "LICENSE": "MIT\n"})
        self.assertFinds(lint.check_links(root), "README.md:1", "evals/README.md")

    def test_web_links_and_anchors_are_not_followed(self):
        root = self.tree({"README.md": "[Claude Code](https://claude.com/claude-code), [up](#top).\n"})
        self.assertClean(lint.check_links(root))

    def test_an_eval_grader_naming_a_missing_skill_is_found(self):
        root = self.tree({**skill("views"),
                          "evals/routing-ai/graders/fires-ai.md":
                              '---\ntype: tool_used\ntool: Skill\ninput_match: "denodo:ai"\n---\n'})
        self.assertFinds(lint.check_links(root), "evals/routing-ai/graders/fires-ai.md:4", "denodo:ai")


class SkillLengthTest(TreeTestCase):
    def _lines(self, n: int) -> str:
        return "".join(f"line {i}\n" for i in range(n))

    def test_an_unlisted_skill_over_the_limit_is_found(self):
        root = self.tree({"skills/views/SKILL.md": self._lines(501)})
        self.assertFinds(lint.check_skill_length(root, ceilings={}), "skills/views/SKILL.md", "501", "500")

    def test_a_listed_skill_that_grew_is_found(self):
        root = self.tree({"skills/views/SKILL.md": self._lines(723)})
        self.assertFinds(lint.check_skill_length(root, ceilings={"views": 722}), "723", "722")

    def test_a_listed_skill_that_shrank_asks_for_the_lower_number(self):
        root = self.tree({"skills/views/SKILL.md": self._lines(700)})
        self.assertFinds(lint.check_skill_length(root, ceilings={"views": 722}), "700")

    def test_a_listed_skill_back_within_the_limit_asks_to_be_unlisted(self):
        root = self.tree({"skills/views/SKILL.md": self._lines(480)})
        self.assertFinds(lint.check_skill_length(root, ceilings={"views": 722}), "views")

    def test_listed_lengths_that_hold_pass(self):
        root = self.tree({"skills/views/SKILL.md": self._lines(722), "skills/vql/SKILL.md": self._lines(500)})
        self.assertClean(lint.check_skill_length(root, ceilings={"views": 722}))


if __name__ == "__main__":
    unittest.main()
