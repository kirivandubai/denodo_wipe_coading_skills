#!/usr/bin/env python3
"""Run the outcome scenarios against a test server and grade what the agent did.

    python3 evals/outcome/run.py --env <profile> [--scenario NAME ...] [--runs N] [--model M]
                                 [--with-writes] [--with-marketplace] [--keep] [--no-judge]

For each scenario and run: the fixture is reset with `scripts/denodo verify` (its manifest's
cleanup, then its steps, kept); headless Claude Code runs the scenario's turns in a fresh project
directory with only the plugin, its tool and the project's files; then the checks read the trace,
the ledger of the agent's session, the project and the server. After a scenario's last run its
fixture is removed, unless --keep.

Why a runner of its own and not `claude plugin eval`: the eval sandbox lets no shell command
open a TCP connection to the server (design: docs/superpowers/specs/2026-10-06-outcome-evals-design.md).
The agent runs here as the operator does — on the operator's credentials and profile, never on a
profile marked production. Every scenario run is a paid agent session; see evals/README.md.

Standard library only; Python 3.11+.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

import checks  # noqa: E402
import scenarios  # noqa: E402
import transcript  # noqa: E402

TOOL = REPO / "scripts" / "denodo"
SYSTEM = """You are working in the project directory of a data team that uses Denodo; it is a git
repository. The Denodo profile for this work is `{env}`, a test server. Nobody will answer
questions while you work: when you finish, or when something needs the human, end with your
message to them — they read it when they are back.

This session's shell runs one program only, the plugin's tool: call it by its full path, one
command per Bash call — no variables, loops, pipes, redirections or `&&` chains, which are
refused. Read and write files with the file tools."""
JUDGE = """You grade one message an AI agent wrote to a human, against one criterion.

Criterion:
{criterion}

The message:
<<<
{message}
>>>

Answer with PASS or FAIL on the first line, then one sentence saying why."""


# --- pure parts (unit-tested) ---------------------------------------------------------------

def claude_command(*, repo: Path, project: Path, model: str | None, max_turns: int, budget: float,
                   system: str, resume: str | None) -> list[str]:
    """The headless agent: the plugin from the repository, nothing of the operator's own setup
    (plugins, hooks, MCP servers, CLAUDE.md), and no tool but the plugin's and the project's files."""
    tools = ["Skill", "Read", "Glob", "Grep", "TodoWrite",
             f"Write(/{project}/**)", f"Edit(/{project}/**)", f"Bash({repo}/scripts/denodo *)"]
    command = ["claude", "-p", "--output-format", "stream-json", "--verbose",
               "--max-turns", str(max_turns), "--max-budget-usd", str(budget),
               "--permission-mode", "dontAsk", "--setting-sources", "project",
               "--strict-mcp-config", "--mcp-config", json.dumps({"mcpServers": {}}),
               "--plugin-dir", str(repo), "--allowedTools", ",".join(tools),
               "--append-system-prompt", system]
    if model:
        command += ["--model", model]
    if resume:
        command += ["--resume", resume]
    return command


def child_env(base: dict, *, session: str, env_name: str) -> dict:
    env = dict(base)
    env.update(DENODO_SESSION=session, DENODO_ENV=env_name, ENABLE_CLAUDEAI_MCP_SERVERS="false")
    return env


def skip_reason(scenario: scenarios.Scenario, *, with_writes: bool, with_marketplace: bool) -> str | None:
    if "writes" in scenario.gates and not with_writes:
        return "creates a table in the server's cache database and writes its rows: run with --with-writes"
    if "marketplace" in scenario.gates and not with_marketplace:
        return "writes to the shared Data Marketplace catalog: run with --with-marketplace"
    return None


def files_reason(scenario: scenarios.Scenario, values: dict) -> str | None:
    if scenario.needs_local_files and not str(values.get("fixture_route", "")).startswith("LOCAL"):
        return ("reads its CSV files from the server's own disk: copy verification/data there and set, in "
                "the values file beside your profiles (verify.toml), fixture_route = \"LOCAL 'LocalConnection'\" "
                "and fixture_base = \"<that folder>\"")
    return None


def fixture_skip(report: dict) -> str | None:
    for step in report.get("steps") or []:
        if step.get("skipped") and step.get("cause") not in (None, "failure", "cleanup-only"):
            return f"fixture step {step.get('id')!r} skipped: {step.get('reason')}"
    return None


def fixture_error(report: dict) -> str | None:
    if report.get("ok"):
        return None
    for step in report.get("steps") or []:
        if not step.get("ok"):
            error = step.get("error") or {}
            return f"fixture step {step.get('id')!r} failed: {error.get('message') or error}"
    error = report.get("error") or {}
    return f"the fixture could not be built: {error.get('message') or error or 'see the verify report'}"


def production_refusal(env_doc: dict) -> str | None:
    env = env_doc.get("env") or {}
    if env.get("production"):
        return f"profile {env.get('name')!r} is marked production: the scenarios run an agent that creates and drops"
    return None


def pending_entries(changes: dict) -> list[str]:
    """What a catalog synchronisation would bring in or take out (modified descriptions excluded)."""
    out = []
    for key in ("serverElements", "localElements"):
        for entry in changes.get(key) or []:
            name = ".".join(str(entry[k]) for k in ("databaseName", "elementName") if entry.get(k))
            out.append(f"{key}: {name}")
    return out


def exact_ids(body: dict, name: str) -> list[int]:
    return [e["id"] for e in (body or {}).get("elements") or [] if e.get("name") == name]


def split_path(path: str) -> tuple[str, list[str]]:
    base, _, query = path.partition("?")
    return base, [f"{k}={v}" for k, v in urllib.parse.parse_qsl(query, keep_blank_values=True)]


def summarise(results: list[dict]) -> tuple[str, int]:
    lines = [f"{'scenario':24} {'run':>3}  {'result':16} {'cost $':>7} {'turns':>5}  failed checks"]
    code = 0
    for r in results:
        if r["status"] == "ran":
            passed = sum(1 for c in r["checks"] if c["passed"])
            verdict = f"{passed}/{len(r['checks'])}"
            failed = ", ".join(c["name"] for c in r["checks"] if not c["passed"])
            if failed:
                code = max(code, 1)
        else:
            verdict, failed = r["status"], r.get("reason", "")
            if r["status"] != "skipped":
                code = 2
        cost = f"{r['cost_usd']:.2f}" if r.get("cost_usd") is not None else "-"
        lines.append(f"{r['scenario']:24} {r['run']:>3}  {verdict:16} {cost:>7} {r.get('turns') or '-':>5}  {failed}")
    return "\n".join(lines), code


# --- the server, through the plugin's tool ----------------------------------------------------

class Tool:
    """`scripts/denodo` as the runner calls it: one JSON document back. The runner's own commands
    run under a session of their own, so nothing the fixture creates is the agent's."""

    def __init__(self, env_name: str, session: str):
        self.env_name, self.session = env_name, session

    def __call__(self, *args: str, timeout: int = 900) -> dict:
        env = {**os.environ, "DENODO_SESSION": self.session}
        completed = subprocess.run([str(TOOL), *args], capture_output=True, text=True, env=env, timeout=timeout)
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError:
            return {"ok": False, "error": {"message": (completed.stdout + completed.stderr)[-2000:]}}

    def verify(self, fixture: Path, *flags: str) -> dict:
        return self("verify", "--env", self.env_name, "--chain", str(fixture), *flags, timeout=1800)


class ScriptServer:
    """What the checks read on the server."""

    def __init__(self, tool: Tool):
        self.tool = tool

    def query(self, vql: str) -> tuple[bool, list, str]:
        doc = self.tool("vql", "run", "--env", self.tool.env_name, "--max-rows", "5000", "-e", vql)
        statements = doc.get("statements") or []
        if not statements:
            return False, [], json.dumps(doc.get("error"))
        last = statements[-1]
        return bool(last.get("ok")), last.get("rows") or [], ((last.get("error") or {}).get("message") or "")

    def get(self, path: str) -> tuple[bool, str]:
        base, params = split_path(path)
        args = ["api", "get", "--env", self.tool.env_name, base]
        for p in params:
            args += ["--param", p]
        doc = self.tool(*args)
        status = doc.get("status") or 0
        body = doc.get("body")
        return bool(doc.get("ok")) and status < 400, json.dumps(body) if not isinstance(body, str) else body


def claude_judge(model: str, workdir: Path):
    def judge(criterion: str, message: str) -> tuple[bool, str]:
        command = ["claude", "-p", "--output-format", "json", "--max-turns", "1", "--permission-mode", "dontAsk",
                   "--setting-sources", "project", "--strict-mcp-config", "--mcp-config",
                   json.dumps({"mcpServers": {}}), "--model", model]
        completed = subprocess.run(command, input=JUDGE.format(criterion=criterion.strip(), message=message),
                                   capture_output=True, text=True, cwd=workdir, timeout=300,
                                   env={**os.environ, "ENABLE_CLAUDEAI_MCP_SERVERS": "false"})
        try:
            answer = json.loads(completed.stdout).get("result", "")
        except json.JSONDecodeError:
            return False, f"the judge did not answer: {completed.stderr[-300:]}"
        first, _, rest = answer.strip().partition("\n")
        return first.strip().upper().startswith("PASS"), " ".join((first + " " + rest).split())[:300]
    return judge


# --- grading a stored run again --------------------------------------------------------------

# Checks of the server's state, and the paid judge: a stored run keeps their verdicts, since the
# state they read is gone and the judge would be paid again.
STORED_KINDS = {"server", "server_api", "final_number", "judge"}


def regrade_run(scenario: scenarios.Scenario, run_dir: Path) -> dict:
    """The checks of one stored run, again: what the trace, the project and the ledger show is
    recomputed with today's checks; the server's and the judge's verdicts are the stored ones."""
    traces = sorted(run_dir.glob("trace-*.jsonl"), key=lambda p: int(p.stem.split("-")[1]))
    merged = transcript.merge([transcript.parse(p.read_text(encoding="utf-8").splitlines(), turn=int(p.stem.split("-")[1]))
                               for p in traces])
    stored_file = run_dir / "checks.json"
    stored = json.loads(stored_file.read_text(encoding="utf-8")) if stored_file.is_file() else {}
    previous = {c["name"]: c for c in stored.get("checks", [])}
    ledger_file = run_dir / "ledger.json"
    ledger = json.loads(ledger_file.read_text(encoding="utf-8")) if ledger_file.is_file() else None
    evidence = checks.Evidence(transcript=merged, project=(run_dir / "project").resolve(), ledger=ledger,
                               values=stored.get("values") or {})
    verdicts = []
    for spec in scenario.checks:
        if spec["kind"] in STORED_KINDS:
            old = previous.get(spec["name"], {"passed": False, "detail": "no stored verdict"})
            verdicts.append({"name": spec["name"], "kind": spec["kind"], "passed": bool(old.get("passed")),
                             "detail": f"{old.get('detail', '')} (stored)"})
        else:
            verdicts.append(checks.run_check(spec, evidence, None, None))
    return {**{k: v for k, v in stored.items() if k != "checks"}, "scenario": scenario.name,
            "run": int(run_dir.name.split("-")[1]), "status": "ran", "checks": verdicts,
            "cost_usd": merged.cost_usd, "turns": merged.turns}


def regrade(results: Path) -> list[dict]:
    known = {s.name: s for s in scenarios.load_all(HERE)}
    out = []
    for run_dir in sorted(results.glob("*/run-*")):
        scenario = known.get(run_dir.parent.name)
        if scenario is None or not list(run_dir.glob("trace-*.jsonl")):
            continue
        result = regrade_run(scenario, run_dir)
        (run_dir / "checks.regraded.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        out.append(result)
    return out


# --- one scenario ----------------------------------------------------------------------------

def ledger_dir() -> Path:
    profiles = os.environ.get("DENODO_PROFILES") or "~/.denodo/profiles.toml"
    return Path(profiles).expanduser().parent / "sessions"


def reset(tool: Tool, scenario: scenarios.Scenario, flags: list[str]) -> tuple[dict | None, str | None, str | None]:
    """(the setup report, why the scenario is skipped, why it failed)."""
    tool.verify(scenario.fixture, "--cleanup-only", *flags)  # a missing leftover fails its DROP: harmless
    report = tool.verify(scenario.fixture, "--keep", *flags)
    skip = fixture_skip(report)
    if skip:
        return report, skip, None
    return report, None, fixture_error(report)


def teardown(tool: Tool, server: ScriptServer, scenario: scenarios.Scenario, flags: list[str]) -> None:
    for entry in scenario.teardown_api:
        ok, body = server.get(entry["lookup"])
        for ident in exact_ids(json.loads(body) if ok else {}, entry["name"]) if ok else []:
            tool("api", "delete", "--env", tool.env_name, entry["delete"].replace("{id}", str(ident)))
    tool.verify(scenario.fixture, "--cleanup-only", *flags)


def catalog_pending(server: ScriptServer) -> list[str]:
    pending = []
    for kind in ("DATABASES", "VIEWS"):
        ok, body = server.get(f"/public/api/element-management/{kind}/changes")
        if not ok:
            return [f"{kind}/changes did not answer: {body[:200]}"]
        pending += pending_entries(json.loads(body))
    return pending


def new_project() -> Path:
    """Outside the repository: Claude Code reads every CLAUDE.md above the working directory."""
    project = Path(tempfile.mkdtemp(prefix="denodo-outcome-")).resolve()
    (project / "README.md").write_text("# Data products\n\nDenodo views of the analytics team.\n", encoding="utf-8")
    for command in (["git", "init", "-q"], ["git", "add", "README.md"],
                    ["git", "-c", "user.name=eval", "-c", "user.email=eval@example.org", "commit", "-q", "-m", "start"]):
        subprocess.run(command, cwd=project, check=True, capture_output=True)
    return project


def run_agent(scenario: scenarios.Scenario, *, values: dict, env_name: str, model: str | None,
              out: Path, session: str) -> tuple[transcript.Transcript, Path, str | None]:
    project = new_project()
    system = SYSTEM.format(env=env_name)
    parts: list[transcript.Transcript] = []
    resume = None
    error = None
    for number, prompt in enumerate(scenario.turns, start=1):
        command = claude_command(repo=REPO, project=project, model=model, max_turns=scenario.max_turns,
                                 budget=scenario.max_budget_usd, system=system, resume=resume)
        trace = out / f"trace-{number}.jsonl"
        try:
            with trace.open("w", encoding="utf-8") as sink:
                subprocess.run(command, input=checks.render(prompt.strip(), {**values, "env": env_name}),
                               stdout=sink, stderr=subprocess.PIPE, text=True, cwd=project,
                               env=child_env(os.environ, session=session, env_name=env_name),
                               timeout=scenario.timeout_seconds)
        except subprocess.TimeoutExpired:
            error = f"turn {number} timed out after {scenario.timeout_seconds} s"
        part = transcript.parse(trace.read_text(encoding="utf-8").splitlines(), turn=number)
        parts.append(part)
        if error or not part.session_id:
            error = error or f"turn {number} ended without a session id"
            break
        resume = part.session_id
    return transcript.merge(parts), project, error


def run_scenario(scenario: scenarios.Scenario, *, args, tool: Tool, server: ScriptServer, out: Path,
                 judge) -> list[dict]:
    flags = [f for f, on in (("--with-writes", args.with_writes), ("--with-marketplace", args.with_marketplace)) if on]
    results = []
    why = skip_reason(scenario, with_writes=args.with_writes, with_marketplace=args.with_marketplace)
    if why:
        return [{"scenario": scenario.name, "run": 0, "status": "skipped", "reason": why, "checks": []}]
    try:
        for number in range(1, args.runs + 1):
            run_out = out / scenario.name / f"run-{number}"
            run_out.mkdir(parents=True)
            base = {"scenario": scenario.name, "run": number, "checks": []}
            if "marketplace" in scenario.gates:
                tool.verify(scenario.fixture, "--cleanup-only", *flags)
                pending = catalog_pending(server)
                if pending:
                    results.append({**base, "status": "skipped", "reason": "the catalog has pending changes this "
                                    "run did not make, which its synchronisations would take along: " + "; ".join(pending[:8])})
                    break
            report, skip, failure = reset(tool, scenario, flags)
            (run_out / "fixture.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            values = (report or {}).get("values") or {}
            skip = skip or files_reason(scenario, values)
            if skip or failure:
                results.append({**base, "status": "skipped" if skip else "fixture failed", "reason": skip or failure})
                break
            session = f"eval-{scenario.name}-{number}-{out.name}"
            started = time.monotonic()
            print(f"[{dt.datetime.now():%H:%M:%S}] {scenario.name} run {number}: agent started", flush=True)
            merged, project, error = run_agent(scenario, values=values, env_name=args.env, model=args.model,
                                               out=run_out, session=session)
            ledger_file = ledger_dir() / f"{session}.json"
            ledger = json.loads(ledger_file.read_text(encoding="utf-8")) if ledger_file.is_file() else None
            evidence = checks.Evidence(transcript=merged, project=project, ledger=ledger, values={**values, "env": args.env})
            verdicts = [checks.run_check(spec, evidence, server, judge) for spec in scenario.checks]
            shutil.copytree(project, run_out / "project", ignore=shutil.ignore_patterns(".git"))
            shutil.rmtree(project, ignore_errors=True)
            for suffix in (".json", ".lock"):
                path = ledger_dir() / f"{session}{suffix}"
                if path.is_file():
                    if suffix == ".json":
                        shutil.copy(path, run_out / "ledger.json")
                    path.unlink()
            result = {**base, "status": "ran", "checks": verdicts, "values": evidence.values, "error": error,
                      "cost_usd": merged.cost_usd,
                      "turns": merged.turns, "seconds": round(time.monotonic() - started),
                      "final": merged.final_text}
            (run_out / "checks.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            failed = [c["name"] for c in verdicts if not c["passed"]]
            print(f"[{dt.datetime.now():%H:%M:%S}] {scenario.name} run {number}: "
                  f"{len(verdicts) - len(failed)}/{len(verdicts)} checks, ${merged.cost_usd or 0:.2f}"
                  + (f"; failed: {', '.join(failed)}" if failed else ""), flush=True)
            results.append(result)
    finally:
        if not args.keep:
            teardown(tool, server, scenario, flags)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--env", default=os.environ.get("DENODO_ENV"), help="profile of a test server")
    parser.add_argument("--scenario", action="append", default=[], help="run only this scenario (repeatable)")
    parser.add_argument("--runs", type=int, default=1, help="runs per scenario (default 1; 3 before a release)")
    parser.add_argument("--model", help="the agent's model (default: Claude Code's default)")
    parser.add_argument("--judge-model", default="sonnet", help="the model of the judge checks (default sonnet)")
    parser.add_argument("--no-judge", action="store_true", help="skip the paid judge checks (they fail)")
    parser.add_argument("--with-writes", action="store_true", help="also dml-preview: a table in the cache database")
    parser.add_argument("--with-marketplace", action="store_true", help="also marketplace-tag: the shared catalog")
    parser.add_argument("--keep", action="store_true", help="leave the last run's fixture and objects on the server")
    parser.add_argument("--results", default=str(HERE / "results"), help="where the results go")
    parser.add_argument("--regrade", metavar="DIR",
                        help="grade the runs stored in DIR again with today's checks, running no agent: the "
                             "server's and the judge's verdicts are kept as stored")
    args = parser.parse_args(argv)
    if args.regrade:
        table, code = summarise(regrade(Path(args.regrade)))
        print(table)
        return code
    if not args.env:
        parser.error("no profile: pass --env or set DENODO_ENV")
    all_scenarios = scenarios.load_all(HERE)
    chosen = [s for s in all_scenarios if not args.scenario or s.name in args.scenario]
    unknown = set(args.scenario) - {s.name for s in all_scenarios}
    if unknown:
        parser.error(f"unknown scenario(s) {sorted(unknown)}; known: {[s.name for s in all_scenarios]}")
    out = Path(args.results) / dt.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    out.mkdir(parents=True)
    tool = Tool(args.env, session=f"eval-fixture-{out.name}")
    refusal = production_refusal(tool("env", "check", "--env", args.env))
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    server = ScriptServer(tool)
    judge = None if args.no_judge else claude_judge(args.judge_model, out)
    results: list[dict] = []
    for scenario in chosen:
        results += run_scenario(scenario, args=args, tool=tool, server=server, out=out, judge=judge)
    for suffix in (".json", ".lock"):  # the fixtures' own ledger: nothing reads it after the run
        (ledger_dir() / f"{tool.session}{suffix}").unlink(missing_ok=True)
    table, code = summarise(results)
    report = {"started": out.name, "env": args.env, "model": args.model, "runs": args.runs,
              "cost_usd": round(sum(r.get("cost_usd") or 0 for r in results), 2), "results": results}
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(table)
    print(f"total ${report['cost_usd']:.2f}; report: {out / 'report.json'}")
    return code


if __name__ == "__main__":
    sys.exit(main())
