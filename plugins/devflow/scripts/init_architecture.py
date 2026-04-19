#!/usr/bin/env python3
"""Initialize a new DevFlow architecture package."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import (
    architecture_dir_for_id,
    create_architecture_files,
    ensure_workspace,
    init_architecture_meta,
    next_architecture_id,
    normalize_module_ids,
    write_architecture_summary,
    write_global_summary,
    write_json,
)


def cleanup_failed_architecture_dir(architecture_dir: Path) -> None:
    if architecture_dir.exists():
        shutil.rmtree(architecture_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a new DevFlow architecture package.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    parser.add_argument("--title", required=True, help="Architecture title")
    parser.add_argument("--request", required=True, help="Initial user request text")
    parser.add_argument(
        "--module",
        action="append",
        default=[],
        help="Module id or label. May be provided multiple times.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    ensure_workspace(workspace)

    architecture_id = next_architecture_id(workspace)
    architecture_dir = architecture_dir_for_id(workspace, architecture_id)
    architecture_dir.mkdir(parents=True, exist_ok=False)

    try:
        module_ids = normalize_module_ids(args.module)
        create_architecture_files(
            architecture_dir,
            args.title,
            args.request,
            architecture_id,
            module_ids,
        )
        meta = init_architecture_meta(architecture_id, args.title, module_ids)
        write_json(architecture_dir / "meta.json", meta)
        write_architecture_summary(architecture_dir)
        write_global_summary(workspace)
        meta = json.loads((architecture_dir / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        cleanup_failed_architecture_dir(architecture_dir)
        raise

    print(
        json.dumps(
            {
                "created": True,
                "architecture_id": architecture_id,
                "architecture_dir": str(architecture_dir),
                "meta": meta,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
