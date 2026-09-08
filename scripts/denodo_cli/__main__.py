# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "denodo-sqlalchemy>=2.0.5",
#     "psycopg2-binary>=2.9.6",
# ]
# ///
"""Entry point: ``python -m denodo_cli ...`` or ``uv run --script denodo_cli/__main__.py ...``.

The PEP 723 block above is the single source of truth for runtime dependencies — the
launcher reads it when it has to build a venv without uv.
"""

import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make ``denodo_cli`` importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from denodo_cli.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
