"""Cross-checks the real chain manifest against the real skill tree, offline.

``RunChainTest`` in ``test_commands_verify.py`` exercises the executor's mechanics
against a synthetic skill fixture — it never touches ``verification/chain.toml`` or the
real ``skills/`` tree, so it cannot catch the two of them drifting apart. A renamed
heading, an edited block, or a substitution that no longer matches breaks ``denodo
verify`` silently: ``python3 -m unittest discover`` stays green, and the breakage only
surfaces on the next live run against a stand.

That drift is fully checkable without a stand: ``load_chain``, ``templates.load_block``
and ``render`` are all pure functions over files already in the repository. This module
loads the real manifest and, for every ``template`` step, resolves its address against
the real repo root and renders its body with the manifest's own ``[values]`` — exactly
what ``verify``'s ``_body()`` does before a step ever touches the network.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from denodo_cli.commands.verify import (PLACEHOLDER, ChainError, load_chain, parse_api_calls,
                                        render)
from denodo_cli.templates import TemplateError, load_block

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "verification" / "chain.toml"


class ChainManifestMatchesSkillsTest(unittest.TestCase):
    def setUp(self):
        self.chain = load_chain(MANIFEST)
        self.visible = self._values_in_order()

    def _values_in_order(self) -> dict[str, dict[str, str]]:
        """What each step's ``render`` sees: ``[values]`` plus everything captured before it.

        ``render`` refuses a substitution naming a value the run does not have — that is the
        typo check this module exists to run offline. A captured value (an http step's
        ``capture``) does not exist until that step has answered, so rendering every step
        against the manifest's ``[values]`` alone would flag the external-element steps,
        which legitimately carry an id captured one step earlier. Replaying the chain's
        order keeps the typo check and adds one more for free: a step using a value nothing
        has captured *yet* fails here rather than halfway through a live run, with
        marketplace objects already created.
        """
        available = dict(self.chain.values)
        per_step: dict[str, dict[str, str]] = {}
        for step in self.chain.steps:
            per_step[step.id] = dict(available)
            for name in step.capture:
                # "0", not a descriptive placeholder: a captured value is a marketplace id,
                # and the rendered body has to stay a parseable api call — a body reading
                # {"externalToolServerIds":[<captured by ...>]} is not JSON, and the step
                # would fail this module for the wrong reason.
                available[name] = "0"
        self.after_every_step = available
        return per_step

    def test_a_step_only_names_values_captured_before_it(self):
        for step in self.chain.steps:
            available = self.visible[step.id]
            for needle, replacement in step.substitute.items():
                for name in {m.group(1) for m in PLACEHOLDER.finditer(replacement)}:
                    with self.subTest(step=step.id, value=name):
                        self.assertIn(
                            name, available,
                            f"step {step.id!r} substitutes {needle!r} with {{{name}}}, which "
                            f"no earlier step captures and [values] does not define")

    def test_every_template_step_resolves_and_renders_against_the_real_skills(self):
        template_steps = [s for s in self.chain.steps if s.kind == "template"]
        self.assertTrue(template_steps, "the manifest has no template steps to check")

        exercised_sales_analytics = False
        for step in template_steps:
            with self.subTest(step=step.id):
                # A broken address (renamed or removed heading) must fail here, naming the
                # step — not surface only once `verify` runs against a live stand.
                try:
                    block = load_block(REPO, step.address)
                except TemplateError as exc:
                    self.fail(f"step {step.id!r}: address {step.address!r} does not "
                             f"resolve against the current skills tree: {exc}")

                # A substitution whose needle no longer occurs in the block (the skill's
                # template text changed under it) must fail here too, not go quiet.
                try:
                    body = render(block.body, step.substitute, self.visible[step.id])
                except ChainError as exc:
                    self.fail(f"step {step.id!r}: substitution against the real block "
                             f"failed: {exc}")

                if "sales_analytics" in step.substitute:
                    # A substitution that stops matching but somehow still "succeeds" (the
                    # needle relocates into the replacement text itself, say) would be a
                    # substitution that silently became a no-op — catch it by checking the
                    # literal is actually gone from the rendered body, not just that
                    # render() did not raise.
                    self.assertNotIn("sales_analytics", body,
                                     f"step {step.id!r}: 'sales_analytics' survived "
                                     f"substitution into the rendered body")
                    exercised_sales_analytics = True

        self.assertTrue(exercised_sales_analytics,
                        "no template step exercised the sales_analytics substitution — "
                        "the no-op check above never ran")

    def test_every_http_step_indexes_calls_the_block_actually_has(self):
        """``calls = [0, 1]`` has to name calls that exist in the block it points at.

        This is the drift this module exists for, in its sharpest form: delete one ``api``
        line from ``skills/marketplace/SKILL.md`` and the manifest's indexes silently shift
        — the step then runs a *different* call, or an index the block no longer has. Only
        a live run would notice, and by then it has already written to a shared catalog.
        """
        http_steps = [s for s in self.chain.steps if s.channel == "http"]
        self.assertTrue(http_steps, "the manifest has no http steps to check")
        for step in http_steps:
            with self.subTest(step=step.id):
                block = load_block(REPO, step.address)
                body = render(block.body, step.substitute, self.visible[step.id])
                try:
                    calls = parse_api_calls(body)
                except ChainError as exc:
                    self.fail(f"step {step.id!r}: the block at {step.address!r} no longer "
                             f"parses as api calls: {exc}")
                self.assertTrue(calls, f"step {step.id!r}: the block has no api calls at all")
                for index in step.calls:
                    self.assertTrue(
                        0 <= index < len(calls),
                        f"step {step.id!r}: calls names index {index}, but the block at "
                        f"{step.address!r} has {len(calls)} api call(s)")

    def test_no_step_and_no_cleanup_entry_names_the_server_itself(self):
        """``serverId`` comes from the profile, never from the manifest or the templates.

        ``RestTransport`` adds ``marketplace_server_id`` to a call only when the call has
        not named a server itself (``transports/api_rest.py``), so a literal ``serverId``
        anywhere in this chain — in a rendered template body or in a cleanup entry —
        silently disables the profile mechanism for everyone: a fork pointing at another
        marketplace could then only change the id by editing this repository. That is the
        gap task T16 closed, and this is what keeps it closed.
        """
        for step in [s for s in self.chain.steps if s.channel == "http"]:
            with self.subTest(step=step.id):
                body = render(load_block(REPO, step.address).body, step.substitute,
                              self.visible[step.id])
                for call in parse_api_calls(body):
                    self.assertNotIn(
                        "serverId", call["params"],
                        f"step {step.id!r}: {call['method']} {call['path']} names the server "
                        f"itself, so the profile's marketplace_server_id is never used")

        for entry in self.chain.cleanup_http:
            with self.subTest(cleanup=entry["path"]):
                self.assertNotIn(
                    "serverId", entry["params"],
                    f"[cleanup] http {entry['method']} {entry['path']} names the server "
                    f"itself, so the profile's marketplace_server_id is never used")
