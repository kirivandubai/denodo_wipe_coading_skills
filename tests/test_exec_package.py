"""The package denodo-exec as an agent installs it: what it ships, what it depends on, and that
the driver it names is the one the launcher installs."""

import ast
import re
import sys
import tomllib
import unittest
from pathlib import Path

import denodo_exec

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
LAYER = REPO / "scripts" / "denodo_exec"
PEP723 = re.compile(r"(?m)^# /// script$\s(?P<content>(^#(| .*)$\s)+)^# ///$")


def _name(specifier: str) -> str:
    return re.split(r"[<>=!~\[; ]", specifier, maxsplit=1)[0].lower()


def _floor(specifier: str) -> str | None:
    found = re.search(r">=\s*([0-9][^,; ]*)", specifier)
    return found.group(1) if found else None


class PackageTest(unittest.TestCase):
    def test_the_version_is_written_once_for_the_tag(self):
        # The tag an agent pins is denodo-exec-v<version>: the wheel's version and the module's
        # must be the same number.
        self.assertEqual(PYPROJECT["project"]["version"], denodo_exec.__version__)
        self.assertEqual(PYPROJECT["project"]["name"], "denodo-exec")

    def test_the_wheel_ships_denodo_cli_unchanged_beside_the_layer(self):
        wheel = PYPROJECT["tool"]["hatch"]["build"]["targets"]["wheel"]
        self.assertEqual(wheel["packages"], ["scripts/denodo_cli", "scripts/denodo_exec"])
        sdist = PYPROJECT["tool"]["hatch"]["build"]["targets"]["sdist"]
        self.assertTrue({"scripts/denodo_cli", "scripts/denodo_exec", "LICENSE"} <= set(sdist["include"]))

    def test_the_driver_extra_is_the_launchers_dependencies(self):
        text = (REPO / "scripts" / "denodo_cli" / "__main__.py").read_text(encoding="utf-8")
        block = "".join(line[2:] for line in PEP723.search(text).group("content").splitlines(True))
        script = tomllib.loads(block)["dependencies"]
        extra = PYPROJECT["project"]["optional-dependencies"]["driver"]
        self.assertEqual({_name(d): _floor(d) for d in extra}, {_name(d): _floor(d) for d in script})

    def test_the_layer_is_standard_library_and_runs_denodo_cli_as_a_process(self):
        # Only the offline planner of the tests imports denodo_cli: everything else runs it as a
        # process, so its transports and their driver are never loaded into a tool server.
        allowed = set(sys.stdlib_module_names) | {"denodo_exec"}
        for path in sorted(LAYER.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                         else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                for name in names:
                    top = name.split(".")[0]
                    with self.subTest(module=path.name, imports=name):
                        if top == "denodo_cli":
                            self.assertEqual(path.name, "offline.py")
                        else:
                            self.assertIn(top, allowed | {"__future__"})

    def test_the_package_needs_nothing_installed(self):
        self.assertEqual(PYPROJECT["project"]["dependencies"], [])
        self.assertEqual(PYPROJECT["project"]["requires-python"], ">=3.11")


if __name__ == "__main__":
    unittest.main()
