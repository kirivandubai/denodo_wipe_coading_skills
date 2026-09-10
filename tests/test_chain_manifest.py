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

from denodo_cli.commands.verify import ChainError, load_chain, render
from denodo_cli.templates import TemplateError, load_block

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "verification" / "chain.toml"


class ChainManifestMatchesSkillsTest(unittest.TestCase):
    def setUp(self):
        self.chain = load_chain(MANIFEST)

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
                    body = render(block.body, step.substitute, self.chain.values)
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
