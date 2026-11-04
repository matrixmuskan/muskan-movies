#!/usr/bin/env python3
"""The injector replaces one placeholder and does not print the token."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "inject_feedback_token.py"
TOKEN = "local-test-token"
SOURCE = 'window.MOVIES_FEEDBACK = { token: "__MOVIES_FEEDBACK_TOKEN__" };\n'


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.js"
        path.write_text(SOURCE, encoding="utf-8")
        env = os.environ.copy()
        env["MOVIES_FEEDBACK_TOKEN"] = TOKEN
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(path)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            raise SystemExit(result.stderr or result.stdout)
        if TOKEN in result.stdout or TOKEN in result.stderr:
            raise SystemExit("injector printed the token")
        updated = path.read_text(encoding="utf-8")
        if "__MOVIES_FEEDBACK_TOKEN__" in updated or TOKEN not in updated:
            raise SystemExit("placeholder was not replaced")
        if "1 placeholder replaced" not in result.stdout:
            raise SystemExit(result.stdout)
    print("ok inject feedback token")


if __name__ == "__main__":
    main()
