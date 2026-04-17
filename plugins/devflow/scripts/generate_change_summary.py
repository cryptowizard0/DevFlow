#!/usr/bin/env python3
"""Generate change-summary.md from the task worktree diff and task dev log."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import normalize_string_list, read_json, read_text, write_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate change-summary.md for a DevFlow task.")
    parser.add_argument("--task-dir", required=True, help="Task directory")
    parser.add_argument("--repo-root", help="Repository root to inspect when task worktree is unavailable")
    return parser.parse_args()


def run_git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return f"[git {' '.join(args)} failed]\n{completed.stderr.strip()}\n"
    return completed.stdout.strip() or "(no output)"


def resolve_repo_root(meta: dict[str, object], repo_root_arg: str | None) -> Path:
    worktree_path_value = meta.get("worktree_path")
    if worktree_path_value:
        worktree_path = Path(str(worktree_path_value)).expanduser().resolve()
        if worktree_path.exists():
            return worktree_path

    if repo_root_arg:
        return Path(repo_root_arg).expanduser().resolve()

    raise SystemExit("Missing usable task worktree_path and --repo-root fallback.")


def main() -> int:
    args = parse_args()
    task_dir = Path(args.task_dir).resolve()
    meta = read_json(task_dir / "meta.json")
    repo_root = resolve_repo_root(meta, args.repo_root)

    dev_log = read_text(task_dir / "dev.md").strip() or "No development notes recorded yet."
    architecture_change_request = (
        read_text(task_dir / "architecture-change-request.md").strip()
        or "No architecture change request recorded."
    )
    status_short = run_git(repo_root, "status", "--short")
    diff_stat = run_git(repo_root, "diff", "--stat")
    cached_diff_stat = run_git(repo_root, "diff", "--cached", "--stat")

    content = "\n".join(
        [
            "# Change Summary",
            "",
            "## Task Worktree",
            "",
            f"- Path: `{repo_root}`",
            f"- Branch: `{meta.get('worktree_branch') or 'n/a'}`",
            f"- Base Ref: `{meta.get('worktree_base_ref') or 'n/a'}`",
            "",
            "## Architecture Binding",
            "",
            f"- Project ID: `{meta.get('project_id') or 'n/a'}`",
            f"- Architecture Version: `{meta.get('architecture_version') or 'n/a'}`",
            f"- Module Scope: {', '.join(normalize_string_list(meta.get('module_scope'))) or 'n/a'}",
            f"- Constraint Refs: {', '.join(normalize_string_list(meta.get('constraint_refs'))) or 'n/a'}",
            f"- Exception IDs: {', '.join(normalize_string_list(meta.get('exception_ids'))) or 'n/a'}",
            f"- Architecture Compliance Status: `{meta.get('architecture_compliance_status') or 'n/a'}`",
            "",
            "## Working Tree",
            "",
            "```text",
            status_short,
            "```",
            "",
            "## Unstaged Diff Stat",
            "",
            "```text",
            diff_stat,
            "```",
            "",
            "## Staged Diff Stat",
            "",
            "```text",
            cached_diff_stat,
            "```",
            "",
            "## Development Log Snapshot",
            "",
            "```md",
            dev_log,
            "```",
            "",
            "## Architecture Change Request Snapshot",
            "",
            "```md",
            architecture_change_request,
            "```",
            "",
        ]
    )
    output_path = task_dir / "change-summary.md"
    write_text(output_path, content)
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
