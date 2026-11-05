#!/usr/bin/env python3
"""Run the PayPal sandbox payout smoke command from the repository root."""

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    venv_python = backend / "venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable
    command = [python, str(backend / "manage.py"), "paypal_smoke", *sys.argv[1:]]
    return subprocess.call(command, cwd=backend, env=os.environ.copy())


if __name__ == "__main__":
    raise SystemExit(main())
