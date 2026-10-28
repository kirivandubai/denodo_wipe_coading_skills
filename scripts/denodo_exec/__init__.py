"""denodo_exec — the Denodo layer of an agent's tool server, installable as one package.

An agent that works on a Denodo server through a tool server of its own needs the same few
things every time: ``denodo_cli`` run as a subprocess on one profile, that profile copied for a
container, the password scrubbed from every answer, a rule of scope read off the plan
``vql plan`` makes, a numbered VQL file read once, planned, judged and applied, a ledger of the
objects it made, and records that hash the same on any runtime. They live here, once, so that a
fix reaches every agent and a new agent installs the layer instead of copying it.

``denodo_cli`` is shipped beside this package in the same distribution (``denodo-exec``) and is
the plugin's own execution layer, unchanged; nothing here imports its transports, and the
``driver`` extra brings the Denodo driver it runs on. Modules:

  errors     the layer's errors: refused (the input must change) and unavailable (ask later)
  canonical  canonical JSON, digests and timestamps
  files      atomic writes, JSON and JSONL records, file digests
  profile    the copy of one profile a containerised denodo_cli is pointed at
  scrub      the password out of every answer
  client     denodo_cli as a process: ``Denodo``
  vql        an independent statement splitter, the other half of the plan's alignment check
  scope      the rule of scope: which planned statement is the agent's to run
  ledger     the objects a workspace made and has not dropped
  vqlfile    a workspace's VQL file: read once, planned, judged, applied, and a check's answer
  offline    ``vql plan`` made by denodo_cli's own planner over a catalog a test supplies

See docs/superpowers/specs/2026-09-04-denodo-skills-design.md, section 7.5.
"""

__version__ = "0.1.0"
