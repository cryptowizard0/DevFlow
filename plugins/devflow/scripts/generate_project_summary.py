#!/usr/bin/env python3
"""Generate summary.md for a DevFlow project."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import write_project_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate summary.md for a DevFlow project.")
    parser.add_argument("--project-dir", required=True, help="Project directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    output_path = write_project_summary(project_dir)
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
