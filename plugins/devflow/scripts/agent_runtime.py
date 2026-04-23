#!/usr/bin/env python3
"""Runtime adapter contracts for DevFlow subagent orchestration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol


RuntimeStatus = Literal["pending", "completed", "failed", "blocked", "unavailable"]
ReviewVerdict = Literal["pass", "changes_requested", "blocked"]


@dataclass
class DispatchResult:
    """Normalized result returned by host-specific subagent dispatch adapters."""

    status: RuntimeStatus
    error: str | None = None
    agent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "error": self.error,
            "agent_id": self.agent_id,
            "metadata": self.metadata,
        }


@dataclass
class SubagentRunResult:
    """Normalized result loaded from a task-scoped result.json."""

    role: str
    run_id: str
    status: RuntimeStatus
    artifact_path: str | None = None
    summary: str | None = None
    error: str | None = None
    verdict: ReviewVerdict | None = None
    files_touched: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "run_id": self.run_id,
            "status": self.status,
            "artifact_path": self.artifact_path,
            "summary": self.summary,
            "error": self.error,
            "verdict": self.verdict,
            "files_touched": self.files_touched,
            "commands": self.commands,
        }


class AgentRuntimeAdapter(Protocol):
    """Adapter for host-specific planner/dev/reviewer execution."""

    def dispatch(
        self,
        role: str,
        request_path: str,
        context_path: str,
        result_path: str,
        task_context_minimal: dict[str, Any],
    ) -> DispatchResult:
        ...


class UnsupportedAgentRuntime:
    """Default adapter for repo-local scripts without host runtime wiring."""

    def dispatch(
        self,
        role: str,
        request_path: str,
        context_path: str,
        result_path: str,
        task_context_minimal: dict[str, Any],
    ) -> DispatchResult:
        task_id = task_context_minimal.get("task_id") or "unknown"
        return DispatchResult(
            status="unavailable",
            error=(
                "No repo-local subagent runtime is configured. "
                f"Handoff files were created for task {task_id} and role {role}; "
                "the host orchestrator must execute the subagent against those files."
            ),
            metadata={
                "request_path": request_path,
                "context_path": context_path,
                "result_path": result_path,
            },
        )


class FixtureAgentRuntime:
    """Test-only adapter that writes completed result files synchronously."""

    def dispatch(
        self,
        role: str,
        request_path: str,
        context_path: str,
        result_path: str,
        task_context_minimal: dict[str, Any],
    ) -> DispatchResult:
        dispatch_status = os.environ.get(f"DEVFLOW_FIXTURE_{role.upper()}_DISPATCH_STATUS") or os.environ.get("DEVFLOW_FIXTURE_DISPATCH_STATUS")
        if dispatch_status in {"failed", "blocked"}:
            error = os.environ.get(f"DEVFLOW_FIXTURE_{role.upper()}_DISPATCH_ERROR") or os.environ.get(
                "DEVFLOW_FIXTURE_DISPATCH_ERROR"
            )
            return DispatchResult(
                status=dispatch_status,
                error=error or f"Fixture {role} dispatch {dispatch_status}.",
            )

        result_file = Path(result_path).expanduser().resolve()
        artifact_path = result_file.parent / "result.md"
        if role == "plan":
            body = os.environ.get("DEVFLOW_FIXTURE_PLAN_BODY", "# Plan\n\nFixture plan.\n")
            payload = {
                "role": role,
                "run_id": result_file.parent.name,
                "status": "completed",
                "artifact_path": str(artifact_path),
                "summary": "Fixture plan generated.",
                "error": None,
                "verdict": None,
                "files_touched": [],
                "commands": [],
            }
        elif role == "dev":
            body = os.environ.get("DEVFLOW_FIXTURE_DEV_NOTES", "Fixture dev notes.\n")
            payload = {
                "role": role,
                "run_id": result_file.parent.name,
                "status": "completed",
                "artifact_path": str(artifact_path),
                "summary": os.environ.get("DEVFLOW_FIXTURE_DEV_SUMMARY", "Fixture dev result"),
                "error": None,
                "verdict": None,
                "files_touched": json.loads(os.environ.get("DEVFLOW_FIXTURE_DEV_FILES", "[]")),
                "commands": json.loads(os.environ.get("DEVFLOW_FIXTURE_DEV_COMMANDS", "[]")),
            }
        elif role == "review":
            body = os.environ.get("DEVFLOW_FIXTURE_REVIEW_BODY", "# Review\n\nFixture review.\n")
            payload = {
                "role": role,
                "run_id": result_file.parent.name,
                "status": "completed",
                "artifact_path": str(artifact_path),
                "summary": "Fixture review completed.",
                "error": None,
                "verdict": os.environ.get("DEVFLOW_FIXTURE_REVIEW_VERDICT", "pass"),
                "files_touched": [],
                "commands": [],
            }
        else:
            return DispatchResult(status="failed", error=f"Unsupported fixture role: {role}")

        artifact_path.write_text(body.rstrip() + "\n", encoding="utf-8")
        result_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return DispatchResult(status="completed", agent_id=f"fixture-{role}", metadata={"result_path": str(result_file)})


def get_runtime_adapter(name: str = "unsupported") -> AgentRuntimeAdapter:
    if name == "unsupported":
        return UnsupportedAgentRuntime()
    if name == "fixture":
        return FixtureAgentRuntime()
    raise ValueError(f"Unknown runtime adapter: {name}")


def load_run_result(result_path: str | Path) -> SubagentRunResult:
    resolved = Path(result_path).expanduser().resolve()
    if not resolved.exists():
        return SubagentRunResult(role="unknown", run_id="unknown", status="pending", artifact_path=None)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return SubagentRunResult(
        role=str(payload.get("role") or "unknown"),
        run_id=str(payload.get("run_id") or "unknown"),
        status=str(payload.get("status") or "pending"),
        artifact_path=payload.get("artifact_path"),
        summary=payload.get("summary"),
        error=payload.get("error"),
        verdict=payload.get("verdict"),
        files_touched=[str(item) for item in (payload.get("files_touched") or [])],
        commands=[str(item) for item in (payload.get("commands") or [])],
    )
