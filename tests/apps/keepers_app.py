"""Harness: espone la sola pagina dei portieri per i test con AppTest."""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asta.ui import viewer  # noqa: E402

viewer.keepers_page()
