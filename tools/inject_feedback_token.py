#!/usr/bin/env python3
"""Replace the feedback token placeholder in the built config.js.

Reads MOVIES_FEEDBACK_TOKEN from the environment. Never prints the token.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PLACEHOLDER = "__MOVIES_FEEDBACK_TOKEN__"


def inject(text: str, token: str) -> str:
    token = token.strip()
    if not token:
        raise SystemExit("MOVIES_FEEDBACK_TOKEN is empty or unset")
    if any(char in token for char in "'\"\\<>\n\r "):
        raise SystemExit("MOVIES_FEEDBACK_TOKEN has unexpected characters")
    found = text.count(PLACEHOLDER)
    if found != 1:
        raise SystemExit(f"expected exactly 1 token placeholder, found {found}")
    updated = text.replace(PLACEHOLDER, token)
    if PLACEHOLDER in updated:
        raise SystemExit("placeholder remained after inject")
    return updated


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: inject_feedback_token.py <config.js>")
    path = Path(sys.argv[1])
    updated = inject(path.read_text(encoding="utf-8"), os.environ.get("MOVIES_FEEDBACK_TOKEN", ""))
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(updated, encoding="utf-8")
    os.replace(temporary, path)
    print(f"injected feedback token into {path.name} (1 placeholder replaced)")


if __name__ == "__main__":
    main()
