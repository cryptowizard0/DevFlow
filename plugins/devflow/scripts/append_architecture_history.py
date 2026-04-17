#!/usr/bin/env python3
"""Append the current architecture snapshot to architecture-history.md."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import now_iso, read_json, read_text, write_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append an architecture snapshot to architecture-history.md.")
    parser.add_argument("--project-dir", required=True, help="Project directory")
    parser.add_argument("--reason", required=True, help="Reason for the architecture update")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    history_path = project_dir / "architecture-history.md"
    history = read_text(history_path).rstrip()
    if not history:
        history = "# Architecture History"

    architecture_text = read_text(project_dir / "architecture.md").rstrip()
    module_map_text = read_text(project_dir / "module-map.md").rstrip()
    standards_text = read_text(project_dir / "standards.md").rstrip()
    roadmap_text = read_text(project_dir / "roadmap.md").rstrip()
    constraints_payload = read_json(project_dir / "constraints.json")

    entry = (
        f"\n\n## Snapshot {now_iso()}\n\n"
        f"- Reason: {args.reason}\n\n"
        "### architecture.md\n\n"
        f"```md\n{architecture_text}\n```\n\n"
        "### module-map.md\n\n"
        f"```md\n{module_map_text}\n```\n\n"
        "### standards.md\n\n"
        f"```md\n{standards_text}\n```\n\n"
        "### roadmap.md\n\n"
        f"```md\n{roadmap_text}\n```\n\n"
        "### constraints.json\n\n"
        f"```json\n{json.dumps(constraints_payload, ensure_ascii=False, indent=2)}\n```\n"
    )
    write_text(history_path, history + entry + "\n")
    print(str(history_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
