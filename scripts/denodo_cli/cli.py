"""Argument parsing and dispatch. Every invocation prints exactly one JSON document on
stdout; exit codes: 0 ok, 1 the server refused, 2 usage/config/refused-destructive,
3 the driver stack is not installed (normally handled by the launcher)."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from . import __version__
from .commands import EXIT_ENVIRONMENT, EXIT_USAGE
from .commands.api import api_call, parse_multipart_specs, parse_params
from .commands.env import check_environment, init_environment, list_environments
from .commands.vql import describe, run_statements
from .commands.verify import ChainError, load_chain, run_chain
from .output import envelope, to_json
from .profiles import ProfileError, load_profile, profiles_path
from .transports import get_rest_transport, get_vql_transport
from .vql_split import split_statements

INSTALL_HINT = "pip install 'denodo-sqlalchemy>=2.0.5' 'psycopg2-binary>=2.9.6'"
DEFAULT_MAX_ROWS = 100


class UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    """argparse that reports usage problems as JSON instead of text on stderr."""

    def error(self, message):
        raise UsageError(message)


def resolve_vql_factory(profile):
    return get_vql_transport(profile.transport)


def resolve_rest_factory():
    return get_rest_transport()


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="denodo", description="Execution layer for the Denodo skills: apply VQL to "
                     "Virtual DataPort and REST calls to Data Marketplace. Output is one JSON document.")
    parser.add_argument("--version", action="version", version=f"denodo-cli {__version__}")
    top = parser.add_subparsers(dest="group", required=True)

    env_opt = argparse.ArgumentParser(add_help=False)
    env_opt.add_argument("--env", help="profile name from the profiles file (default: $DENODO_ENV)")

    vql = top.add_parser("vql", help="VQL against Virtual DataPort").add_subparsers(dest="action", required=True)
    run = vql.add_parser("run", parents=[env_opt], help="run a .vql file (or '-' for stdin, or -e STATEMENTS)")
    run.add_argument("file", nargs="?", help="path to a .vql file, or '-' to read stdin")
    run.add_argument("-e", "--execute", metavar="VQL", help="VQL text to run instead of a file")
    run.add_argument("--database", help="connect to this database instead of the profile's")
    run.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS, help="rows kept per result set")
    run.add_argument("--continue-on-error", action="store_true", help="keep going after a failed statement")
    run.add_argument("--allow-destructive", action="store_true",
                     help="required on a production profile for DROP/ALTER/DELETE statements")
    desc = vql.add_parser("desc", parents=[env_opt], help="DESC [VQL] <type> <name>")
    desc.add_argument("name")
    desc.add_argument("--type", default="view", help="object type, e.g. view, table, 'datasource df', database")
    desc.add_argument("--vql", action="store_true", help="return the server-generated VQL (DESC VQL)")
    desc.add_argument("--database")
    desc.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)

    api = top.add_parser("api", parents=[env_opt], help="one REST call to Data Marketplace")
    api.add_argument("method", help="get, post, put, delete, ...")
    api.add_argument("path", help="path under marketplace_url, e.g. /public/api/tags")
    api.add_argument("--json", metavar="TEXT", help="JSON request body")
    api.add_argument("--json-file", metavar="FILE", help="file with the JSON request body")
    api.add_argument("--param", action="append", default=[], metavar="K=V", help="query parameter (repeatable)")
    api.add_argument("--part", action="append", default=[], metavar="FIELD=@FILE|json:...|TEXT",
                     help="multipart part (repeatable); implies multipart/form-data")
    api.add_argument("--timeout", type=float, default=300, help="seconds (synchronize calls can be slow)")
    api.add_argument("--allow-destructive", action="store_true",
                     help="required on a production profile for DELETE and set-replacing POST calls")

    env = top.add_parser("env", help="environment profiles").add_subparsers(dest="action", required=True)
    env.add_parser("list", help="profiles known on this machine (never shows passwords)")
    env.add_parser("check", parents=[env_opt], help="connect to VDP (and Data Marketplace if configured)")
    env.add_parser("init", help="create a profile interactively — run it yourself, e.g. `! scripts/denodo env init`")

    verify = top.add_parser("verify", parents=[env_opt],
                            help="run the chain of skill templates against a stand and clean up")
    verify.add_argument("--chain", help="manifest path (default: verification/chain.toml in the repo)")
    verify.add_argument("--database", help="test database to create and drop (default: from the manifest)")
    verify.add_argument("--with-marketplace", action="store_true",
                        help="also run the Data Marketplace tail; it writes outside your own database")
    verify.add_argument("--keep", action="store_true", help="leave the created objects on the stand")
    verify.add_argument("--update-marks", action="store_true",
                        help="rewrite the verified: mark of every template step that passed")
    verify.add_argument("--allow-destructive", action="store_true",
                        help="required on a production profile: the whole run creates and then drops "
                             "objects, so without this flag it is refused before it creates anything")
    return parser


def _profile(args):
    name = args.env or os.environ.get("DENODO_ENV")
    if not name:
        raise UsageError("no environment given: pass --env <profile> or set DENODO_ENV "
                         "(see `denodo env list`)")
    return load_profile(name)


def _read_vql(args) -> tuple[str, str]:
    if bool(args.file) == bool(args.execute):
        raise UsageError("give exactly one input: a .vql file, '-' for stdin, or -e VQL")
    if args.execute:
        return args.execute, "<inline>"
    if args.file == "-":
        return sys.stdin.read(), "<stdin>"
    path = Path(args.file).expanduser()
    if not path.is_file():
        raise UsageError(f"file not found: {path}")
    return path.read_text(encoding="utf-8"), str(path)


def _json_body(args):
    if args.json and args.json_file:
        raise UsageError("use either --json or --json-file, not both")
    text = args.json
    if args.json_file:
        path = Path(args.json_file).expanduser()
        if not path.is_file():
            raise UsageError(f"file not found: {path}")
        text = path.read_text(encoding="utf-8")
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise UsageError(f"request body is not valid JSON: {exc}") from exc


def _dispatch(args) -> tuple[dict, int]:
    if args.group == "env" and args.action == "list":
        return list_environments(profiles_path())
    if args.group == "env" and args.action == "init":
        if not sys.stdin.isatty():
            raise UsageError("env init is interactive: run it yourself in a terminal "
                             "(in Claude Code: `! scripts/denodo env init`) so the password is typed "
                             "into a hidden prompt and never enters a transcript")
        def ask(prompt, default=""):
            suffix = f" [{default}]" if default else ""
            return input(f"{prompt}{suffix}: ") or default
        return init_environment(profiles_path(), ask=ask, ask_secret=getpass.getpass)

    profile = _profile(args)
    if args.group == "env":  # check
        return check_environment(profile, vql_factory=resolve_vql_factory(profile),
                                 rest_factory=resolve_rest_factory())
    if args.group == "vql" and args.action == "run":
        text, source = _read_vql(args)
        doc, code = run_statements(profile, split_statements(text), transport_factory=resolve_vql_factory(profile),
                                   max_rows=args.max_rows, database=args.database,
                                   allow_destructive=args.allow_destructive,
                                   continue_on_error=args.continue_on_error)
        doc["source"] = source
        return doc, code
    if args.group == "vql" and args.action == "desc":
        return describe(profile, args.name, kind=args.type, vql=args.vql, database=args.database,
                        transport_factory=resolve_vql_factory(profile), max_rows=args.max_rows)
    if args.group == "api":
        try:
            params = parse_params(args.param)
            multipart = parse_multipart_specs(args.part) or None
        except ValueError as exc:
            raise UsageError(str(exc)) from exc
        return api_call(profile, args.method, args.path, transport_factory=resolve_rest_factory(),
                        json_body=_json_body(args), params=params, multipart=multipart,
                        timeout=args.timeout, allow_destructive=args.allow_destructive)
    if args.group == "verify":
        repo = Path(__file__).resolve().parents[2]
        manifest = Path(args.chain).expanduser() if args.chain else repo / "verification" / "chain.toml"
        # run_chain raises ChainError too, not just load_chain: _check_cleanup_placeholders
        # runs inside it, and with a user-supplied --chain that is the likeliest first
        # failure. Both are the same class of problem — a manifest that does not hold
        # together — so both come out as the one JSON usage error, never as a traceback.
        try:
            chain = load_chain(manifest)
            return run_chain(profile, chain, root=repo, vql_factory=resolve_vql_factory(profile),
                             rest_factory=resolve_rest_factory(), database=args.database,
                             with_marketplace=args.with_marketplace, keep=args.keep,
                             update_marks=args.update_marks, allow_destructive=args.allow_destructive)
        except ChainError as exc:
            raise UsageError(str(exc)) from exc
    raise UsageError("unknown command")  # pragma: no cover — argparse rejects it first


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    command = " ".join(a for a in argv[:2] if not a.startswith("-"))
    try:
        args = build_parser().parse_args(argv)
        doc, code = _dispatch(args)
    except UsageError as exc:
        doc, code = envelope(False, None, command, error={"kind": "usage", "message": str(exc)}), EXIT_USAGE
    except (ProfileError, KeyError) as exc:
        message = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
        doc, code = envelope(False, None, command, error={"kind": "config", "message": message}), EXIT_USAGE
    except ImportError as exc:
        doc, code = envelope(False, None, command, error={
            "kind": "environment",
            "message": f"the Denodo driver stack is not importable: {exc}",
            "hint": INSTALL_HINT,
        }), EXIT_ENVIRONMENT
    print(to_json(doc))
    return code
