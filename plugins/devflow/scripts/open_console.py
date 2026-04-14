#!/usr/bin/env python3
"""Resolve and optionally open the bundled DevFlow workspace console."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open the bundled DevFlow workspace console in the default browser."
    )
    parser.add_argument(
        "--print-path",
        action="store_true",
        help="Only print the resolved console path without opening a browser.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    console_path = script_dir.parent / "assets" / "console" / "index.html"

    if not console_path.exists():
      print(f"Missing console entry: {console_path}", file=sys.stderr)
      return 1

    print(console_path)

    if not args.print_path:
        webbrowser.open(console_path.as_uri())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
