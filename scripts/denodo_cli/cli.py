"""Argument parsing and dispatch. Every invocation prints exactly one JSON document on
stdout; exit codes: 0 ok, 1 the server refused, 2 usage/config/refused-destructive,
3 the driver stack is not installed (normally handled by the launcher)."""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import sys
from pathlib import Path

from . import __version__
from .commands import EXIT_ENVIRONMENT, EXIT_USAGE
from .commands.api import api_call, parse_multipart_specs, parse_params
from .commands.env import check_environment, init_environment, list_environments
from .commands.plan import list_ledger, plan_input
from .commands.secret import encrypt_password
from .commands.testing import DEFAULT_DB_ADAPTER, run_testing_tool, write_testing_config
from .commands.vql import describe, run_statements
from .commands.verify import ChainError, default_values_path, load_chain, load_values_file, run_chain
from .features import FEATURE_NAMES
from .ledger import Ledger, prune_sessions, session_from_env
from .output import envelope, to_json
from .profiles import ProfileError, load_profile, profiles_path
from .transports import get_rest_transport, get_vql_transport
from .transports.api_rest import SERVERS as REST_SERVERS
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
                     "Virtual DataPort and REST calls to Data Marketplace and the Scheduler. Output is one "
                     "JSON document.")
    parser.add_argument("--version", action="version", version=f"denodo-cli {__version__}")
    top = parser.add_subparsers(dest="group", required=True)

    env_opt = argparse.ArgumentParser(add_help=False)
    env_opt.add_argument("--env", help="profile name from the profiles file (default: $DENODO_ENV)")

    vql = top.add_parser("vql", help="VQL against Virtual DataPort").add_subparsers(dest="action", required=True)
    run = vql.add_parser("run", parents=[env_opt], help="run a .vql file (or '-' for stdin, or -e STATEMENTS)")
    run.add_argument("file", nargs="?", help="path to a .vql file, or '-' to read stdin")
    run.add_argument("-e", "--execute", metavar="VQL", action="append",
                     help="VQL text to run instead of a file; repeat it for several, in order")
    run.add_argument("--database", help="connect to this database instead of the profile's")
    run.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS, help="rows kept per result set")
    run.add_argument("--continue-on-error", action="store_true", help="keep going after a failed statement")
    run.add_argument("--allow-destructive", action="store_true",
                     help="required on a production profile for DROP/ALTER/DELETE statements")
    plan = vql.add_parser("plan", parents=[env_opt],
                          help="what a .vql file (or '-' / -e) would do on this server, statement by statement: "
                               "new or existing, this session's own, and whether the core's safety table puts it "
                               "under the human's yes; executes nothing")
    plan.add_argument("file", nargs="?", help="path to a .vql file, or '-' to read stdin")
    plan.add_argument("-e", "--execute", metavar="VQL", action="append",
                     help="VQL text to plan instead of a file; repeat it for several, in order")
    plan.add_argument("--database", help="plan against this database instead of the profile's")
    vql.add_parser("ledger", parents=[env_opt],
                   help="the objects this session created on the profile's server, each re-checked against it")
    desc = vql.add_parser("desc", parents=[env_opt], help="DESC [VQL] <type> <name>")
    desc.add_argument("name")
    desc.add_argument("--type", default="view", help="object type, e.g. view, table, 'datasource df', database")
    desc.add_argument("--vql", action="store_true", help="return the server-generated VQL (DESC VQL)")
    desc.add_argument("--database")
    desc.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)

    api = top.add_parser("api", parents=[env_opt], help="one REST call to Data Marketplace or the Scheduler")
    api.add_argument("--server", choices=REST_SERVERS, default="marketplace",
                     help="marketplace (default): path under marketplace_url; scheduler: path under the "
                          "Scheduler administration tool, the profile's Scheduler server added as uri")
    api.add_argument("method", help="get, post, put, delete, ...")
    api.add_argument("path", help="path under the server's base URL, e.g. /public/api/tags")
    api.add_argument("--json", metavar="TEXT", help="JSON request body")
    api.add_argument("--json-file", metavar="FILE", help="file with the JSON request body")
    api.add_argument("--param", action="append", default=[], metavar="K=V", help="query parameter (repeatable)")
    api.add_argument("--part", action="append", default=[], metavar="FIELD=@FILE|json:...|TEXT",
                     help="multipart part (repeatable); implies multipart/form-data")
    api.add_argument("--timeout", type=float, default=300, help="seconds (synchronize calls can be slow)")
    api.add_argument("--allow-destructive", action="store_true",
                     help="required on a production profile for DELETE and set-replacing POST calls")
    api.add_argument("--plan", action="store_true",
                     help="do not send the call: say whether the core's safety table puts it under the human's yes; "
                          "for a catalog synchronize, read both changes and check the radius against this session's ledger")

    secret = top.add_parser("secret", help="credentials for data sources").add_subparsers(dest="action",
                                                                                          required=True)
    secret.add_parser("encrypt", parents=[env_opt],
                      help="encrypt a password for USERPASSWORD … ENCRYPTED; the password is typed into a "
                           "hidden prompt or piped in on stdin, never passed as an argument")

    testing = top.add_parser("testing", help="the Denodo Testing Tool").add_subparsers(dest="action",
                                                                                     required=True)
    testing_config = testing.add_parser(
        "config", parents=[env_opt],
        help="write the Testing Tool's configuration.properties from a profile, beside the profiles file "
             "and never into a git work tree; the password goes into the file, not into the output")
    testing_config.add_argument("--database", help="database the tests connect to (default: the profile's)")
    testing_config.add_argument("--output", metavar="PATH",
                                help="where to write it instead of <profiles dir>/testing/<env>/<database>.properties; "
                                     "refused inside a git work tree unless the repository ignores the path")
    testing_config.add_argument("--db-adapter", default=DEFAULT_DB_ADAPTER,
                                help="folder of the VDP JDBC driver under the tool's drivers/ "
                                     f"(default: {DEFAULT_DB_ADAPTER})")
    testing_config.add_argument("--allow-destructive", action="store_true",
                                help="required on a production profile: the tool runs a suite's SETUP and "
                                     "TEARDOWN statements unchecked")
    testing_run = testing.add_parser(
        "run", parents=[env_opt],
        help="run a folder (or file) of .denodotest tests with the Denodo Testing Tool, its configuration in a "
             "temporary file for this run only; answers with the exit code, the summary and each test")
    testing_run.add_argument("tests", help="a .denodotest file or a folder of them")
    testing_run.add_argument("--database", help="database the tests connect to (default: the profile's)")
    testing_run.add_argument("--tool", metavar="DIR",
                             help="directory the Testing Tool was unzipped into (default: $DENODO_TESTING_TOOL_HOME)")
    testing_run.add_argument("--java-home", metavar="DIR",
                             help="Java 17+ for the tool (default: JAVA_HOME of the environment, else java on PATH)")
    testing_run.add_argument("--db-adapter", default=DEFAULT_DB_ADAPTER,
                             help=f"folder of the VDP JDBC driver under the tool's drivers/ (default: {DEFAULT_DB_ADAPTER})")
    testing_run.add_argument("--allow-destructive", action="store_true",
                             help="required on a production profile: the tool runs a suite's SETUP and "
                                  "TEARDOWN statements unchecked")

    env = top.add_parser("env", help="environment profiles").add_subparsers(dest="action", required=True)
    env.add_parser("list", help="profiles known on this machine (never shows passwords)")
    env.add_parser("check", parents=[env_opt], help="connect to VDP (and Data Marketplace if configured); report whether the user is an administrator and may impersonate")
    env.add_parser("init", help="create a profile interactively — run it yourself, e.g. `! scripts/denodo env init`")

    verify = top.add_parser("verify", parents=[env_opt],
                            help="run the chain of skill templates against a live server and clean up")
    verify.add_argument("--chain", help="manifest path (default: verification/chain.toml in the repo)")
    verify.add_argument("--database", help="test database to create and drop (default: from the manifest)")
    verify.add_argument("--with-marketplace", action="store_true",
                        help="also run the Data Marketplace tail; it writes outside your own database")
    verify.add_argument("--with-ai", action="store_true",
                        help="also run the steps that call the server's LLM; every row they project is "
                             "a paid request")
    verify.add_argument("--with-writes", action="store_true",
                        help="also run the steps that create a table in the source database named in the "
                             "manifest and insert, update and delete its rows")
    verify.add_argument("--with-scheduler", action="store_true",
                        help="also run the Scheduler tail: it creates a project on the shared Scheduler, "
                             "creates and runs jobs there, and deletes the project in cleanup")
    verify.add_argument("--testing-tool", metavar="DIR",
                        help="also run the .denodotest templates with the Denodo Testing Tool installed in DIR "
                             "(its bin/denodo-test.sh needs Java on PATH or in JAVA_HOME)")
    verify.add_argument("--without", metavar="FEATURE", action="append", default=[], choices=FEATURE_NAMES,
                        help="treat the server as lacking this feature (repeatable): its steps are skipped, "
                             "as on a server without it — to rehearse a smaller server, or to skip the steps "
                             "that cache")
    verify.add_argument("--values", metavar="FILE",
                        help="values of this installation, one table per profile (default: verify.toml "
                             "beside the profiles file)")
    verify.add_argument("--keep", action="store_true", help="leave the created objects on the server")
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


def _open_ledger() -> tuple[Ledger | None, str | None]:
    """The session's ledger beside the profiles file, touched so it knows when the session started.
    Never fails a command: without a session id, or when the directory cannot be written, it is off."""
    session, source = session_from_env(os.environ)
    if not session:
        return None, None
    directory = profiles_path().expanduser().parent / "sessions"
    ledger = Ledger(directory, session)
    now = dt.datetime.now(dt.timezone.utc)
    try:
        ledger.touch(now)
        prune_sessions(directory, now)
    except OSError:
        return None, None
    return ledger, source


def _read_vql(args) -> tuple[str, str]:
    if bool(args.file) == bool(args.execute):
        raise UsageError("give exactly one input: a .vql file, '-' for stdin, or -e VQL")
    if args.execute:
        return ";\n".join(args.execute), "<inline>"
    if args.file == "-":
        return sys.stdin.read(), "<stdin>"
    path = Path(args.file).expanduser()
    if not path.is_file():
        raise UsageError(f"file not found: {path}")
    return path.read_text(encoding="utf-8"), str(path)


def _read_password() -> str:
    """The password for ``secret encrypt``: a hidden prompt in a terminal, stdin otherwise.

    Both ways keep it out of the command line, and so out of the session transcript. Only
    the line ending is stripped — spaces can be part of a password, a newline cannot.
    """
    if sys.stdin.isatty():
        password = getpass.getpass("Password to encrypt (hidden): ")
    else:
        password = sys.stdin.read()
        if password.endswith("\n"):
            password = password[:-1]
        if password.endswith("\r"):
            password = password[:-1]
    if not password:
        raise UsageError("no password on stdin: pipe it in, or run the command yourself in a "
                         "terminal (in Claude Code: `! scripts/denodo secret encrypt --env <env>`) "
                         "to type it into a hidden prompt")
    if "\n" in password or "\r" in password:
        raise UsageError("the password must be one line; got several, so nothing was encrypted")
    return password


def _absolute_source(source: str) -> str:
    """A file path as the ledger keeps it: absolute, so it means the same thing from any directory."""
    if source.startswith("<"):
        return source
    return str(Path(source).expanduser().absolute())


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
    ledger, session_source = _open_ledger()
    if args.group == "env":  # check
        return check_environment(profile, vql_factory=resolve_vql_factory(profile),
                                 rest_factory=resolve_rest_factory())
    if args.group == "vql" and args.action == "run":
        text, source = _read_vql(args)
        doc, code = run_statements(profile, split_statements(text), transport_factory=resolve_vql_factory(profile),
                                   max_rows=args.max_rows, database=args.database,
                                   allow_destructive=args.allow_destructive,
                                   continue_on_error=args.continue_on_error,
                                   ledger=ledger, source=_absolute_source(source))
        doc["source"] = source
        return doc, code
    if args.group == "vql" and args.action == "plan":
        text, source = _read_vql(args)
        doc, code = plan_input(profile, split_statements(text), transport_factory=resolve_vql_factory(profile),
                               database=args.database, source=None if source.startswith("<") else source,
                               ledger=ledger, session_source=session_source)
        doc["source"] = source
        return doc, code
    if args.group == "vql" and args.action == "ledger":
        return list_ledger(profile, transport_factory=resolve_vql_factory(profile), ledger=ledger,
                           session_source=session_source)
    if args.group == "testing" and args.action == "run":
        tool = args.tool or os.environ.get("DENODO_TESTING_TOOL_HOME")
        if not tool:
            raise UsageError("no Testing Tool: pass --tool <the directory it was unzipped into> or set "
                             "DENODO_TESTING_TOOL_HOME; the tool is a download from the Denodo support site")
        return run_testing_tool(profile, tests=Path(args.tests), tool=Path(tool), database=args.database,
                                java_home=Path(args.java_home) if args.java_home else None,
                                db_adapter=args.db_adapter, allow_destructive=args.allow_destructive)
    if args.group == "testing":  # config
        return write_testing_config(profile, config_dir=profiles_path().parent / "testing",
                                    database=args.database,
                                    output=Path(args.output) if args.output else None,
                                    db_adapter=args.db_adapter, allow_destructive=args.allow_destructive)
    if args.group == "secret":  # encrypt
        return encrypt_password(profile, _read_password(), transport_factory=resolve_vql_factory(profile))
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
                        timeout=args.timeout, allow_destructive=args.allow_destructive, server=args.server,
                        plan=args.plan, ledger=ledger)
    if args.group == "verify":
        repo = Path(__file__).resolve().parents[2]
        manifest = Path(args.chain).expanduser() if args.chain else repo / "verification" / "chain.toml"
        # run_chain raises ChainError too, not just load_chain: _check_cleanup_placeholders
        # runs inside it, and with a user-supplied --chain that is the likeliest first
        # failure. Both are the same class of problem — a manifest that does not hold
        # together — so both come out as the one JSON usage error, never as a traceback.
        try:
            chain = load_chain(manifest)
            values_path = Path(args.values).expanduser() if args.values else default_values_path()
            if args.values and not values_path.is_file():
                raise ChainError(f"the values file {values_path} does not exist")
            file_values = load_values_file(values_path, profile.name, chain.settable_values(),
                                           own=chain.known_values() - chain.settable_values())
            return run_chain(profile, chain, root=repo, vql_factory=resolve_vql_factory(profile),
                             file_values=file_values, values_file=values_path if values_path.is_file() else None,
                             assume_missing=tuple(dict.fromkeys(args.without)),
                             rest_factory=resolve_rest_factory(), database=args.database,
                             with_marketplace=args.with_marketplace, with_ai=args.with_ai,
                             with_writes=args.with_writes, with_scheduler=args.with_scheduler,
                             testing_tool=Path(args.testing_tool).expanduser().absolute() if args.testing_tool else None,
                             keep=args.keep,
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
