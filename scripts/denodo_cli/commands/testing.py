"""``testing config`` and ``testing run``: the Denodo Testing Tool, configured from a profile.

The Testing Tool is Denodo's own runner for ``.denodotest`` files; the plugin has no runner
of its own. It connects over JDBC with the credentials of a ``configuration.properties``
file — the one thing in a test suite that must not reach git, and that an agent writing it
by hand would have to put a password into, through a command line or a file it types.

This command writes that file from the profile instead. The password goes from the
profiles file straight into a file of the same standing: beside it, readable by the owner
only (0600, in a 0700 directory), never printed and never inside a git work tree — an
explicit ``--output`` there is refused unless the repository ignores the path, since any
other file in a work tree is one ``git add -A`` away from a commit. The answer names the path and the connection without the password.

On a profile marked production the file is refused without ``--allow-destructive``: the
Testing Tool executes every ``SETUP``, ``TEARDOWN`` and ``[script]`` statement of a suite
itself, past the classifier every other command applies, so the human's yes has to come
before the channel exists, not after.

``testing run`` starts the tool itself on a folder of tests — still the tool, not a runner of
the plugin's own: it parses and compares, this only launches it. The configuration goes into
a temporary 0600 file for the one run, so no command ever names a file that holds a password
(a session's permission layer may refuse such a path), the launcher starts from the tool's
``bin/`` (it logs to ``../log`` of its working directory), and the answer carries the exit
code and the summary together — the launcher exits 0 after printing its usage, and a
misnamed test file is skipped without a word, so neither alone means "passed".
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from . import EXIT_EXECUTION, EXIT_OK, EXIT_USAGE
from ..output import envelope
from ..profiles import Profile

COMMAND = "testing config"
DATASOURCE = "vdp"
DRIVER_CLASS = "com.denodo.vdp.jdbc.Driver"
DEFAULT_DB_ADAPTER = "denodo-9.0.0"
CONNECTION_TEST_QUERY = "SELECT * FROM Dual()"
REPORTER = "com.denodo.connect.testing.reporter.ConsoleTestReporter"


def properties_value(text: str) -> str:
    """``text`` escaped for a ``.properties`` value read by ``java.util.Properties``.

    The Testing Tool reads the file as ISO-8859-1, so everything outside printable ASCII
    becomes a ``\\uXXXX`` escape (UTF-16 code units, a surrogate pair beyond the basic
    plane); a leading space would be eaten as separator whitespace, so it is escaped too.
    """
    out: list[str] = []
    for index, char in enumerate(text):
        if char == "\\":
            out.append("\\\\")
        elif char == "\t":
            out.append("\\t")
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif char == "\f":
            out.append("\\f")
        elif char == " " and index == 0:
            out.append("\\ ")
        elif " " <= char <= "~":
            out.append(char)
        else:
            units = char.encode("utf-16-be")
            for i in range(0, len(units), 2):
                out.append(f"\\u{units[i] << 8 | units[i + 1]:04x}")
    return "".join(out)


def _inside_git_work_tree(path: Path) -> Path | None:
    """The work tree ``path`` would land in, or ``None``.

    A ``.git`` directory marks a repository, a ``.git`` file a linked worktree or a
    submodule; either way the file would sit where ``git add`` reaches it.
    """
    for parent in path.parents:
        if (parent / ".git").exists():
            return parent
    return None


def _ignored_by_git(repository: Path, path: Path) -> bool:
    """Whether the repository's ignore rules exclude ``path`` — a home directory kept in git
    ignores its ``.denodo`` the same way. Without a ``git`` to ask, the answer is no."""
    git = shutil.which("git")
    if git is None:
        return False
    try:
        done = subprocess.run([git, "-C", str(repository), "check-ignore", "-q", str(path)],
                              capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def _render(profile: Profile, database: str, jdbc_url: str, db_adapter: str) -> str:
    lines = [
        f"# Denodo Testing Tool configuration for profile '{profile.name}', database '{database}'.",
        "# Written by `denodo testing config` from the profiles file. It holds a password:",
        "# do not copy it into a repository; run the command again instead of editing it.",
        "encoding=UTF-8",
        "maxRowsInMemoryForMatching=10000",
        f"reporter={REPORTER}",
        f"{DATASOURCE}.driverClassName={DRIVER_CLASS}",
        f"{DATASOURCE}.dbAdapter={properties_value(db_adapter)}",
        f"{DATASOURCE}.jdbcUrl={properties_value(jdbc_url)}",
        f"{DATASOURCE}.username={properties_value(profile.user)}",
        f"{DATASOURCE}.password={properties_value(profile.password)}",
        f"{DATASOURCE}.connectionTestQuery={CONNECTION_TEST_QUERY}",
    ]
    return "\n".join(lines) + "\n"


def _write_private(path: Path, text: str) -> None:
    """Replace ``path`` with ``text``, never letting the content exist with wider rights."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")  # created 0600
    try:
        with os.fdopen(fd, "w", encoding="iso-8859-1") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    os.chmod(path, 0o600)


def write_testing_config(profile: Profile, *, config_dir: Path, database: str | None = None,
                         output: Path | None = None, db_adapter: str = DEFAULT_DB_ADAPTER,
                         allow_destructive: bool = False) -> tuple[dict, int]:
    database = profile.database if database is None else database

    def failure(kind: str, message: str) -> tuple[dict, int]:
        return envelope(False, profile, COMMAND, database=database or None,
                        error={"kind": kind, "message": message}), EXIT_USAGE

    if not database or database.startswith(".") or any(c in database for c in "/\\"):
        return failure("usage", f"{database!r} is not a database name")
    if profile.password.startswith("ENC(") and profile.password.endswith(")"):
        return failure("config", f"the password of profile {profile.name!r} has the form ENC(…), which the "
                                 "Testing Tool reads as Jasypt ciphertext and fails to decrypt; nothing was "
                                 "written")
    if profile.production and not allow_destructive:
        return envelope(False, profile, COMMAND, database=database, error={
            "kind": "refused",
            "message": f"profile {profile.name!r} is marked production. The Testing Tool runs every SETUP, "
                       "TEARDOWN and [script] statement of a suite itself, unchecked by this tool. Show the "
                       "human what the suite runs; with their yes, repeat with --allow-destructive.",
        }), EXIT_USAGE

    target = Path(output).expanduser() if output else Path(config_dir) / profile.name / f"{database}.properties"
    target = target.absolute()
    repository = _inside_git_work_tree(target)
    if repository is not None and not _ignored_by_git(repository, target):
        return failure("usage", f"{target} is inside the git work tree {repository} and not ignored by it; "
                                "the file holds a password. Leave --output out (the default is beside the "
                                "profiles file) or name a path outside every repository")

    jdbc_url = f"jdbc:denodo://{profile.host}:{profile.jdbc_port}/{database}"
    _write_private(target, _render(profile, database, jdbc_url, db_adapter))
    return envelope(True, profile, COMMAND, database=database, path=str(target), datasource=DATASOURCE,
                    jdbc_url=jdbc_url, user=profile.user, db_adapter=db_adapter), EXIT_OK


RUN_COMMAND = "testing run"
LAUNCHER = Path("bin") / "denodo-test.sh"
SPECIAL_FILES = ("first.denodotest", "last.denodotest")
TEST_END = re.compile(r"^--\[TEST:END\]\[(?P<status>[A-Z]+)\](?:\[[^\]]*\]){4}\s*Test run: (?P<name>.*?)\. "
                      r"(?P<message>.*)$")
TESTS_RUN = re.compile(r"^Tests run: (?P<run>\d+), OK: (?P<ok>\d+)(?: \(FAILED: (?P<failed>\d+)\))?")
ZERO_TUPLE = re.compile(r"Zero-tuple tests: (?P<zero>\d+)")
TAIL_LINES = 30


def launch_process(command: list[str], cwd: str, env: dict | None) -> tuple[int, str]:
    """The Testing Tool's launcher, run for real: exit code and everything it printed."""
    try:
        done = subprocess.run(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=1800)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return 124, output + "\n(timed out after 1800 s)"
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def parse_output(output: str) -> tuple[list[dict], dict | None]:
    """The tests the console reporter printed — once each, it prints a failure twice — and its summary."""
    tests, seen = [], set()
    summary = None
    zero = None
    for raw in output.splitlines():
        line = raw.strip()
        found = TEST_END.match(line)
        if found and line not in seen:
            seen.add(line)
            tests.append({"test": found["name"], "status": found["status"], "message": found["message"]})
        found = TESTS_RUN.match(line)
        if found:
            summary = {"run": int(found["run"]), "ok": int(found["ok"]), "failed": int(found["failed"] or 0)}
        found = ZERO_TUPLE.search(line)
        if found:
            zero = int(found["zero"])
    if summary is not None:
        summary["zero_tuple"] = zero
    return tests, summary


def count_test_files(tests: Path) -> int | None:
    """``.denodotest`` files the tool should report, or ``None`` when an index decides instead."""
    if tests.is_file():
        return 1
    if any(tests.rglob("*.denodoidx")):
        return None
    return sum(1 for f in tests.rglob("*.denodotest") if f.name not in SPECIAL_FILES)


def run_testing_tool(profile: Profile, *, tests: Path, tool: Path, database: str | None = None,
                     java_home: Path | None = None, runner: Callable | None = None,
                     db_adapter: str = DEFAULT_DB_ADAPTER, allow_destructive: bool = False) -> tuple[dict, int]:
    database = profile.database if database is None else database

    def usage(message: str) -> tuple[dict, int]:
        return envelope(False, profile, RUN_COMMAND, database=database or None,
                        error={"kind": "usage", "message": message}), EXIT_USAGE

    launcher = Path(tool).expanduser().absolute() / LAUNCHER
    if not launcher.is_file():
        return usage(f"no Testing Tool launcher at {launcher}: --tool (or DENODO_TESTING_TOOL_HOME) names the "
                     "directory the tool was unzipped into")
    tests = Path(tests).expanduser().absolute()
    if not tests.exists():
        return usage(f"no tests at {tests}")
    env = dict(os.environ)
    if java_home:
        env["JAVA_HOME"] = str(Path(java_home).expanduser().absolute())
    with tempfile.TemporaryDirectory(prefix="denodo-testing-") as tmp:
        config = Path(tmp) / "configuration.properties"
        doc, code = write_testing_config(profile, config_dir=Path(tmp), database=database, output=config,
                                         db_adapter=db_adapter, allow_destructive=allow_destructive)
        if code != EXIT_OK:
            doc["command"] = RUN_COMMAND
            return doc, code
        returncode, output = (runner or launch_process)(
            ["bash", str(launcher), f"file:{config}", f"file:{tests}"], str(launcher.parent), env)
    results, summary = parse_output(output)
    files = count_test_files(tests)
    ok = (returncode == 0 and summary is not None and summary["run"] > 0
          and summary["ok"] == summary["run"])
    fields: dict = {"tests_path": str(tests), "tool": str(launcher.parents[1]), "exit_code": returncode,
                    "summary": summary, "test_files": files, "tests": results}
    if summary is not None and files is not None and summary["run"] != files:
        fields["warning"] = (f"the tool reported {summary['run']} test(s) run, the folder holds {files} "
                             ".denodotest file(s): a file it did not recognise was skipped, or one failed to load")
    if not ok:
        fields["output_tail"] = "\n".join(output.strip().splitlines()[-TAIL_LINES:])
    return envelope(ok, profile, RUN_COMMAND, database=database, **fields), EXIT_OK if ok else EXIT_EXECUTION
