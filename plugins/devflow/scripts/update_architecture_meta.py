#!/usr/bin/env python3
"""Update DevFlow architecture metadata through explicit transitions or key assignments."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import (
    architecture_dir_for_id,
    load_architecture_meta,
    normalize_module_ids,
    now_iso,
    write_architecture_summary,
    write_global_summary,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update DevFlow architecture meta.json.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    parser.add_argument("--architecture-id", required=True, help="Architecture ID.")
    parser.add_argument(
        "--transition",
        choices=["outline-ready", "published", "discovering"],
        help="Named state transition to apply before custom fields.",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Set a JSON-like value on meta.json. VALUE is parsed as JSON when possible.",
    )
    parser.add_argument("--clear", action="append", default=[], metavar="KEY", help="Clear a key by setting it to null.")
    return parser.parse_args()


def parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def apply_transition(meta: dict[str, Any], transition: str) -> None:
    if transition == "discovering":
        meta["status"] = "discovering"
    elif transition == "outline-ready":
        meta["status"] = "outline_ready"
        meta["outline_version"] = int(meta.get("outline_version", 0)) + 1
    elif transition == "published":
        meta["status"] = "published"


def normalize_architecture_meta(meta: dict[str, Any]) -> None:
    raw_module_ids = meta.get("module_ids") or []
    raw_linked_task_ids = meta.get("linked_task_ids") or []
    meta["module_ids"] = normalize_module_ids([str(item) for item in raw_module_ids])
    meta["linked_task_ids"] = sorted({str(item) for item in raw_linked_task_ids})


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    meta_path, meta = load_architecture_meta(workspace, args.architecture_id)

    if args.transition:
        apply_transition(meta, args.transition)

    for item in args.set:
        if "=" not in item:
            raise SystemExit(f"Invalid --set value: {item}")
        key, raw_value = item.split("=", 1)
        meta[key] = parse_value(raw_value)

    for key in args.clear:
        meta[key] = None

    normalize_architecture_meta(meta)
    meta["updated_at"] = now_iso()
    write_json(meta_path, meta)
    write_architecture_summary(architecture_dir_for_id(workspace, args.architecture_id))
    write_global_summary(workspace)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    print(
        json.dumps(
            {"updated": True, "meta_path": str(meta_path), "meta": meta},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
