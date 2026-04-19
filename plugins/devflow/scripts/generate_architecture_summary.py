#!/usr/bin/env python3
"""Generate summary.md for a DevFlow architecture package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import write_architecture_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate summary.md for a DevFlow architecture package.")
    parser.add_argument("--architecture-dir", required=True, help="Architecture directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    architecture_dir = Path(args.architecture_dir).resolve()
    output_path = write_architecture_summary(architecture_dir)
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
