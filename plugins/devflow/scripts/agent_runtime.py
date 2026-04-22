#!/usr/bin/env python3
"""Runtime adapter contracts for DevFlow orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


RuntimeStatus = Literal["completed", "failed", "blocked", "unavailable"]
ReviewVerdict = Literal["pass", "changes_requested", "blocked"]


@dataclass
class RuntimeResult:
    """Normalized result returned by planner/reviewer runtime adapters."""

    status: RuntimeStatus
    artifact_body: str | None = None
    error: str | None = None
    agent_id: str | None = None
    session_resumable: bool = False
    verdict: ReviewVerdict | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "artifact_body": self.artifact_body,
            "error": self.error,
            "agent_id": self.agent_id,
            "session_resumable": self.session_resumable,
            "verdict": self.verdict,
            "metadata": self.metadata,
        }


class AgentRuntimeAdapter(Protocol):
    """Adapter for host-specific planner/reviewer execution."""

    def request_plan(self, task_context: dict[str, Any]) -> RuntimeResult:
        ...

    def request_review(self, task_context: dict[str, Any]) -> RuntimeResult:
        ...


class UnsupportedAgentRuntime:
    """Default adapter for repo-local scripts without host runtime wiring."""

    def request_plan(self, task_context: dict[str, Any]) -> RuntimeResult:
        task_id = task_context.get("task_id") or "unknown"
        return RuntimeResult(
            status="unavailable",
            error=(
                "No repo-local planner runtime is configured. "
                f"Task {task_id} must receive a plan artifact from the host orchestrator."
            ),
        )

    def request_review(self, task_context: dict[str, Any]) -> RuntimeResult:
        task_id = task_context.get("task_id") or "unknown"
        return RuntimeResult(
            status="unavailable",
            error=(
                "No repo-local reviewer runtime is configured. "
                f"Task {task_id} must receive a review artifact from the host orchestrator."
            ),
        )


def get_runtime_adapter(name: str = "unsupported") -> AgentRuntimeAdapter:
    if name == "unsupported":
        return UnsupportedAgentRuntime()
    raise ValueError(f"Unknown runtime adapter: {name}")
