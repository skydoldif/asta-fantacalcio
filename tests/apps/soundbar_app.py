"""Harness: disegna la sola soundbar, che vive nella barra laterale."""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asta.ui import soundbar  # noqa: E402

soundbar.render_sidebar()
