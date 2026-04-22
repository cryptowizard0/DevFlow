#!/usr/bin/env python3
"""Focused tests for DevFlow task orchestration helpers."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from devflow_lib import evaluate_gate, init_meta, write_json
from orchestrator_lib import load_task_context, update_task_state


SCRIPT_DIR = Path(__file__).resolve().parent
ORCHESTRATE_TASK = SCRIPT_DIR / "orchestrate_task.py"


def make_workspace() -> tuple[Path, Path, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="devflow-tests-"))
    (temp_root / ".git").mkdir()
    workspace = temp_root / "DevFlowWorkspace"
    task_dir = workspace / "tasks" / "TASK-900"
    task_dir.mkdir(parents=True)
    return temp_root, workspace, task_dir


def seed_task(task_dir: Path, meta: dict[str, object]) -> None:
    write_json(task_dir / "meta.json", meta)
    for name, content in {
        "request.md": "# Request\n\nRequest.\n",
        "plan.md": "# Plan\n\nPlan.\n",
        "plan-history.md": "# Plan History\n",
        "dev.md": "# Development Log\n",
        "change-summary.md": "# Change Summary\n\nPending.\n",
        "review.md": "# Review\n\nPending.\n",
        "summary.md": "# Summary\n\nPending.\n",
    }.items():
        (task_dir / name).write_text(content, encoding="utf-8")


class OrchestratorKernelTests(unittest.TestCase):
    def test_dev_gate_requires_next_action_dev(self) -> None:
        meta = {
            "task_id": "TASK-900",
            "status": "developing",
            "next_action": "review",
            "is_blocked": False,
            "execution_mode": "manual",
            "auto_loop_state": None,
        }
        gate = evaluate_gate("dev", meta, "TASK-900")
        self.assertFalse(gate.allowed)

    def test_review_started_uses_reviewer_id_to_mark_live(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "developing"
        meta["next_action"] = "review"
        seed_task(task_dir, meta)

        context = load_task_context(workspace, "TASK-900")
        context = update_task_state(
            context,
            transition="review-started",
            set_fields={
                "reviewer_agent_id": "reviewer-123",
                "reviewer_session_resumable": True,
            },
        )
        self.assertEqual(context.meta["reviewer_agent_id"], "reviewer-123")
        self.assertEqual(context.meta["reviewer_agent_status"], "live")
        self.assertTrue(context.meta["reviewer_session_resumable"])

    def test_resume_dispatches_dev_slice_when_auto_dev_running(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "plan_approved"
        meta["next_action"] = "dev"
        meta["execution_mode"] = "auto_dev"
        meta["auto_loop_state"] = "running"
        seed_task(task_dir, meta)

        completed = subprocess.run(
            [
                "python3",
                str(ORCHESTRATE_TASK),
                "--workspace",
                str(workspace),
                "--task-id",
                "TASK-900",
                "--action",
                "resume",
                "--dev-summary",
                "Resume dev slice",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["next_action"], "review")
        dev_log = (task_dir / "dev.md").read_text(encoding="utf-8")
        self.assertIn("Resume dev slice", dev_log)

    def test_resume_without_inputs_stays_inspection_only(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "plan_approved"
        meta["next_action"] = "dev"
        meta["execution_mode"] = "auto_dev"
        meta["auto_loop_state"] = "running"
        seed_task(task_dir, meta)

        completed = subprocess.run(
            [
                "python3",
                str(ORCHESTRATE_TASK),
                "--workspace",
                str(workspace),
                "--task-id",
                "TASK-900",
                "--action",
                "resume",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["resumable_step"], "dev")
        self.assertEqual(payload["next_action"], "dev")
        dev_log = (task_dir / "dev.md").read_text(encoding="utf-8")
        self.assertNotIn("## Slice", dev_log)

    def test_resume_initial_plan_recovers_without_bumping_plan_version(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "planning"
        meta["is_blocked"] = True
        meta["block_reason"] = "waiting for planner"
        meta["current_step"] = "awaiting planner result for initial plan"
        meta["planner_agent_id"] = "planner-123"
        meta["planner_agent_status"] = "live"
        meta["planner_session_resumable"] = True
        seed_task(task_dir, meta)

        completed = subprocess.run(
            [
                "python3",
                str(ORCHESTRATE_TASK),
                "--workspace",
                str(workspace),
                "--task-id",
                "TASK-900",
                "--action",
                "resume",
                "--plan-body",
                "# Plan\n\nRecovered initial plan.\n",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["next_action"], "approve-plan")
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(saved_meta["plan_version"], 1)
        self.assertEqual(saved_meta["planner_agent_status"], "stale")
        self.assertFalse(saved_meta["planner_session_resumable"])
        history = (task_dir / "plan-history.md").read_text(encoding="utf-8")
        self.assertEqual(history, "# Plan History\n")

    def test_resume_blocked_initial_plan_accepts_late_artifact(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "planning"
        meta["is_blocked"] = True
        meta["block_reason"] = "planner unavailable"
        meta["current_step"] = "planner unavailable while creating task plan"
        seed_task(task_dir, meta)

        completed = subprocess.run(
            [
                "python3",
                str(ORCHESTRATE_TASK),
                "--workspace",
                str(workspace),
                "--task-id",
                "TASK-900",
                "--action",
                "resume",
                "--plan-body",
                "# Plan\n\nLate artifact.\n",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["next_action"], "approve-plan")
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertFalse(saved_meta["is_blocked"])
        self.assertEqual(saved_meta["plan_version"], 1)

    def test_resume_revised_plan_from_non_planning_status(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "developing"
        meta["next_action"] = "dev"
        meta["current_step"] = "awaiting planner result for revised plan"
        meta["planner_agent_id"] = "planner-456"
        meta["planner_agent_status"] = "live"
        meta["planner_session_resumable"] = True
        meta["plan_version"] = 2
        seed_task(task_dir, meta)

        completed = subprocess.run(
            [
                "python3",
                str(ORCHESTRATE_TASK),
                "--workspace",
                str(workspace),
                "--task-id",
                "TASK-900",
                "--action",
                "resume",
                "--plan-body",
                "# Plan\n\nRevised plan body.\n",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["next_action"], "approve-plan")
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(saved_meta["status"], "planning")
        self.assertEqual(saved_meta["plan_version"], 3)
        history = (task_dir / "plan-history.md").read_text(encoding="utf-8")
        self.assertIn("Plan revised through orchestrator", history)

    def test_approve_plan_requires_completed_plan_artifact(self) -> None:
        meta = {
            "task_id": "TASK-900",
            "status": "planning",
            "next_action": "update-plan",
            "is_blocked": False,
            "execution_mode": "manual",
            "auto_loop_state": None,
        }
        gate = evaluate_gate("approve-plan", meta, "TASK-900")
        self.assertFalse(gate.allowed)

    def test_resume_stays_inspection_only_when_waiting_for_user_approval(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "planning"
        meta["next_action"] = "approve-plan"
        meta["plan_version"] = 2
        meta["current_step"] = "awaiting user approval for revised plan"
        seed_task(task_dir, meta)
        original_plan = "# Plan\n\nApproved candidate.\n"
        (task_dir / "plan.md").write_text(original_plan, encoding="utf-8")

        completed = subprocess.run(
            [
                "python3",
                str(ORCHESTRATE_TASK),
                "--workspace",
                str(workspace),
                "--task-id",
                "TASK-900",
                "--action",
                "resume",
                "--plan-body",
                "# Plan\n\nUnexpected replacement.\n",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["next_action"], "approve-plan")
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(saved_meta["plan_version"], 2)
        self.assertEqual((task_dir / "plan.md").read_text(encoding="utf-8"), original_plan)


if __name__ == "__main__":
    unittest.main()
