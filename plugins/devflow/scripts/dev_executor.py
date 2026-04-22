#!/usr/bin/env python3
"""Execution-plane helpers for DevFlow development slices."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

import sys

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from devflow_lib import now_iso, read_text, write_text


@dataclass
class DevExecutionResult:
    status: str
    summary: str
    notes: str | None = None
    files_touched: list[str] | None = None
    commands: list[str] | None = None
    next_action: str = "review"
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "summary": self.summary,
            "notes": self.notes,
            "files_touched": self.files_touched or [],
            "commands": self.commands or [],
            "next_action": self.next_action,
            "error": self.error,
        }


def _render_list(items: list[str], empty_text: str) -> str:
    if not items:
        return f"- {empty_text}"
    return "\n".join(f"- `{item}`" for item in items)


def append_dev_log(
    task_dir: Path,
    summary: str,
    notes: str | None = None,
    files_touched: list[str] | None = None,
    commands: list[str] | None = None,
) -> Path:
    summary = summary.strip()
    if not summary:
        raise ValueError("Development summary is required.")

    files_touched = [item.strip() for item in (files_touched or []) if item.strip()]
    commands = [item.strip() for item in (commands or []) if item.strip()]
    existing = read_text(task_dir / "dev.md").rstrip()
    if not existing:
        existing = "# Development Log"

    entry_lines = [
        "",
        "",
        f"## Slice {now_iso()}",
        "",
        f"- Summary: {summary}",
        "- Files Touched:",
        _render_list(files_touched, "No files recorded."),
        "- Commands:",
        _render_list(commands, "No commands recorded."),
        "",
        "### Notes",
        "",
        (notes or "No additional notes recorded.").rstrip(),
    ]
    write_text(task_dir / "dev.md", existing + "\n".join(entry_lines).rstrip() + "\n")
    return task_dir / "dev.md"


def run_dev_slice(
    task_dir: Path,
    summary: str,
    notes: str | None = None,
    files_touched: list[str] | None = None,
    commands: list[str] | None = None,
) -> DevExecutionResult:
    try:
        append_dev_log(
            task_dir,
            summary=summary,
            notes=notes,
            files_touched=files_touched,
            commands=commands,
        )
    except ValueError as exc:
        return DevExecutionResult(status="failed", summary=summary, error=str(exc))

    return DevExecutionResult(
        status="completed",
        summary=summary,
        notes=notes,
        files_touched=files_touched or [],
        commands=commands or [],
    )
