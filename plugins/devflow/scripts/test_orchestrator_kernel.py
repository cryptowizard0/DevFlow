#!/usr/bin/env python3
"""Focused tests for DevFlow task orchestration helpers."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from devflow_lib import init_meta, write_json
from orchestrator_lib import create_run_spec, load_task_context


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
    (task_dir / "subagent-runs").mkdir(parents=True, exist_ok=True)
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


def run_cli(*args: str, env: dict[str, str] | None = None) -> dict[str, object]:
    merged_env = None
    if env:
        merged_env = dict(os.environ)
        merged_env.update(env)
    completed = subprocess.run(
        ["python3", str(ORCHESTRATE_TASK), *args],
        check=False,
        capture_output=True,
        text=True,
        env=merged_env,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return json.loads(completed.stdout)


class OrchestratorKernelTests(unittest.TestCase):
    def test_resume_planning_task_creates_plan_handoff_files(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        seed_task(task_dir, meta)

        payload = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "resume")
        self.assertEqual(payload["active_subagent_role"], "plan")
        self.assertEqual(payload["active_subagent_run_id"], "PLAN-001")
        run_dir = task_dir / "subagent-runs" / "PLAN-001"
        self.assertTrue((run_dir / "request.json").exists())
        self.assertTrue((run_dir / "context.md").exists())
        self.assertTrue((run_dir / "result.md").exists())
        self.assertTrue((run_dir / "result.json").exists())
        result_payload = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result_payload["status"], "pending")

    def test_resume_finalizes_completed_plan_run_from_result_files(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        seed_task(task_dir, meta)

        run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "resume")
        spec = create_run_spec(task_dir, "plan", "PLAN-001")
        spec.result_md_path.write_text("# Plan\n\nRecovered initial plan.\n", encoding="utf-8")
        write_json(
            spec.result_json_path,
            {
                "role": "plan",
                "run_id": "PLAN-001",
                "status": "completed",
                "artifact_path": str(spec.result_md_path),
                "summary": "Recovered initial plan.",
                "error": None,
                "verdict": None,
                "files_touched": [],
                "commands": [],
            },
        )

        payload = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "resume")
        self.assertEqual(payload["next_action"], "approve-plan")
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertIsNone(saved_meta["active_subagent_role"])
        self.assertEqual(saved_meta["last_subagent_role"], "plan")
        self.assertEqual(saved_meta["last_subagent_run_id"], "PLAN-001")
        self.assertIn("Recovered initial plan.", (task_dir / "plan.md").read_text(encoding="utf-8"))

    def test_resume_pending_plan_run_reuses_same_run_id(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        seed_task(task_dir, meta)

        first = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "resume")
        second = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "resume")
        self.assertEqual(first["active_subagent_run_id"], "PLAN-001")
        self.assertEqual(second["active_subagent_run_id"], "PLAN-001")
        run_dirs = [path.name for path in (task_dir / "subagent-runs").iterdir() if path.is_dir()]
        self.assertEqual(run_dirs, ["PLAN-001"])

    def test_dev_action_creates_pending_run_and_resume_finalizes_to_review(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "plan_approved"
        meta["next_action"] = "dev"
        seed_task(task_dir, meta)

        payload = run_cli(
            "--workspace",
            str(workspace),
            "--task-id",
            "TASK-900",
            "--action",
            "dev",
            "--dev-summary",
            "Focus on parser cleanup",
        )
        self.assertEqual(payload["active_subagent_role"], "dev")
        spec = create_run_spec(task_dir, "dev", "DEV-001")
        spec.result_md_path.write_text("Implemented parser cleanup and tightened state handling.", encoding="utf-8")
        write_json(
            spec.result_json_path,
            {
                "role": "dev",
                "run_id": "DEV-001",
                "status": "completed",
                "artifact_path": str(spec.result_md_path),
                "summary": "Implement parser cleanup",
                "error": None,
                "verdict": None,
                "files_touched": ["src/parser.py"],
                "commands": ["pytest tests/test_parser.py"],
            },
        )

        resumed = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "resume")
        self.assertEqual(resumed["next_action"], "review")
        self.assertIn("Implement parser cleanup", (task_dir / "dev.md").read_text(encoding="utf-8"))
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertIsNone(saved_meta["active_subagent_role"])
        self.assertEqual(saved_meta["last_subagent_role"], "dev")

    def test_repeat_dev_focus_does_not_finalize_active_run(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "plan_approved"
        meta["next_action"] = "dev"
        seed_task(task_dir, meta)

        first = run_cli(
            "--workspace",
            str(workspace),
            "--task-id",
            "TASK-900",
            "--action",
            "dev",
            "--dev-summary",
            "Focus on parser cleanup",
        )
        self.assertEqual(first["active_subagent_run_id"], "DEV-001")

        second = run_cli(
            "--workspace",
            str(workspace),
            "--task-id",
            "TASK-900",
            "--action",
            "dev",
            "--dev-summary",
            "Focus on parser cleanup",
        )
        self.assertEqual(second["active_subagent_role"], "dev")
        self.assertEqual(second["active_subagent_run_id"], "DEV-001")
        self.assertEqual(second["next_action"], "dev")
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(saved_meta["active_subagent_run_id"], "DEV-001")
        self.assertEqual(saved_meta["next_action"], "dev")

    def test_resume_can_finalize_active_dev_run_when_result_metadata_is_supplied(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "plan_approved"
        meta["next_action"] = "dev"
        seed_task(task_dir, meta)

        first = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "dev")
        self.assertEqual(first["active_subagent_run_id"], "DEV-001")

        resumed = run_cli(
            "--workspace",
            str(workspace),
            "--task-id",
            "TASK-900",
            "--action",
            "resume",
            "--dev-summary",
            "Implement parser cleanup",
            "--dev-notes",
            "Implemented parser cleanup and tightened state handling.",
            "--dev-file",
            "src/parser.py",
            "--dev-command",
            "pytest tests/test_parser.py",
        )
        self.assertEqual(resumed["next_action"], "review")
        self.assertIn("Implement parser cleanup", (task_dir / "dev.md").read_text(encoding="utf-8"))
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertIsNone(saved_meta["active_subagent_role"])
        self.assertEqual(saved_meta["last_subagent_role"], "dev")

    def test_failed_run_clears_active_subagent_fields(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        seed_task(task_dir, meta)

        run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "resume")
        spec = create_run_spec(task_dir, "plan", "PLAN-001")
        write_json(
            spec.result_json_path,
            {
                "role": "plan",
                "run_id": "PLAN-001",
                "status": "failed",
                "artifact_path": str(spec.result_md_path),
                "summary": None,
                "error": "planner crashed",
                "verdict": None,
                "files_touched": [],
                "commands": [],
            },
        )

        payload = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "resume")
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["active_subagent_role"])
        self.assertEqual(payload["run_result"]["status"], "failed")
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertTrue(saved_meta["is_blocked"])
        self.assertIsNone(saved_meta["active_subagent_role"])
        self.assertEqual(saved_meta["last_subagent_role"], "plan")

    def test_resume_redispatches_blocked_dev_task_after_failed_run_cleanup(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "plan_approved"
        meta["next_action"] = "dev"
        seed_task(task_dir, meta)

        first = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "dev")
        self.assertEqual(first["active_subagent_run_id"], "DEV-001")
        spec = create_run_spec(task_dir, "dev", "DEV-001")
        write_json(
            spec.result_json_path,
            {
                "role": "dev",
                "run_id": "DEV-001",
                "status": "failed",
                "artifact_path": str(spec.result_md_path),
                "summary": None,
                "error": "dev crashed",
                "verdict": None,
                "files_touched": [],
                "commands": [],
            },
        )

        blocked = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "resume")
        self.assertTrue(blocked["ok"])
        self.assertIsNone(blocked["active_subagent_role"])

        resumed = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "resume")
        self.assertEqual(resumed["active_subagent_role"], "dev")
        self.assertEqual(resumed["active_subagent_run_id"], "DEV-002")
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertFalse(saved_meta["is_blocked"])
        self.assertEqual(saved_meta["active_subagent_run_id"], "DEV-002")

    def test_resume_redispatches_blocked_review_task_after_failed_run_cleanup(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "developing"
        meta["next_action"] = "review"
        seed_task(task_dir, meta)

        first = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "review")
        self.assertEqual(first["active_subagent_run_id"], "REVIEW-001")
        spec = create_run_spec(task_dir, "review", "REVIEW-001")
        write_json(
            spec.result_json_path,
            {
                "role": "review",
                "run_id": "REVIEW-001",
                "status": "failed",
                "artifact_path": str(spec.result_md_path),
                "summary": None,
                "error": "review crashed",
                "verdict": None,
                "files_touched": [],
                "commands": [],
            },
        )

        blocked = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "resume")
        self.assertTrue(blocked["ok"])
        self.assertIsNone(blocked["active_subagent_role"])
        self.assertEqual(blocked["status"], "developing")
        self.assertEqual(blocked["next_action"], "review")

        resumed = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "resume")
        self.assertEqual(resumed["active_subagent_role"], "review")
        self.assertEqual(resumed["active_subagent_run_id"], "REVIEW-002")
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertFalse(saved_meta["is_blocked"])
        self.assertEqual(saved_meta["active_subagent_run_id"], "REVIEW-002")

    def test_resume_preserves_review_blocked_verdict(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "developing"
        meta["next_action"] = "review"
        seed_task(task_dir, meta)

        blocked = run_cli(
            "--workspace",
            str(workspace),
            "--task-id",
            "TASK-900",
            "--action",
            "review",
            "--review-body",
            "# Review\n\nBlocked by missing production credential.\n",
            "--review-verdict",
            "blocked",
        )
        self.assertTrue(blocked["ok"])
        self.assertEqual(blocked["status"], "developing")
        self.assertEqual(blocked["next_action"], "review")

        resumed = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "resume")
        self.assertTrue(resumed["ok"])
        self.assertEqual(resumed["status"], "developing")
        self.assertEqual(resumed["next_action"], "review")
        self.assertIsNone(resumed["active_subagent_role"])
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertTrue(saved_meta["is_blocked"])
        self.assertEqual(saved_meta["current_step"], "task blocked by review")

    def test_review_dispatch_failure_returns_to_resumable_review_state(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "developing"
        meta["next_action"] = "review"
        seed_task(task_dir, meta)

        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "DEVFLOW_FIXTURE_REVIEW_DISPATCH_STATUS": "failed",
            "DEVFLOW_FIXTURE_REVIEW_DISPATCH_ERROR": "review dispatch crashed",
        }
        payload = run_cli(
            "--workspace",
            str(workspace),
            "--task-id",
            "TASK-900",
            "--action",
            "review",
            "--runtime",
            "fixture",
            env=env,
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "developing")
        self.assertEqual(payload["next_action"], "review")
        self.assertIsNone(payload["active_subagent_role"])
        blocked_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertTrue(blocked_meta["is_blocked"])
        self.assertEqual(blocked_meta["block_reason"], "review dispatch crashed")

        resumed = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "resume")
        self.assertEqual(resumed["active_subagent_role"], "review")
        self.assertEqual(resumed["active_subagent_run_id"], "REVIEW-002")
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertFalse(saved_meta["is_blocked"])
        self.assertEqual(saved_meta["active_subagent_run_id"], "REVIEW-002")

    def test_review_pass_still_requires_explicit_done(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "developing"
        meta["next_action"] = "review"
        seed_task(task_dir, meta)

        payload = run_cli(
            "--workspace",
            str(workspace),
            "--task-id",
            "TASK-900",
            "--action",
            "review",
            "--review-body",
            "# Review\n\nLooks good.\n",
            "--review-verdict",
            "pass",
        )
        self.assertEqual(payload["next_action"], "done")
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(saved_meta["status"], "developing")

        done_payload = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "done")
        self.assertEqual(done_payload["status"], "done")

    def test_auto_dev_action_dispatches_dev_run_when_running(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "plan_approved"
        meta["next_action"] = "dev"
        seed_task(task_dir, meta)

        payload = run_cli("--workspace", str(workspace), "--task-id", "TASK-900", "--action", "auto-dev")
        self.assertEqual(payload["active_subagent_role"], "dev")
        self.assertEqual(payload["active_subagent_run_id"], "DEV-001")
        self.assertTrue((task_dir / "subagent-runs" / "DEV-001" / "request.json").exists())
        self.assertEqual(payload["activation"], "started")

    def test_sync_dev_runtime_finalizes_without_extra_resume(self) -> None:
        _, workspace, task_dir = make_workspace()
        meta = init_meta("TASK-900", "Test Task", str(task_dir), "codex/devflow/TASK-900", "main")
        meta["status"] = "plan_approved"
        meta["next_action"] = "dev"
        seed_task(task_dir, meta)

        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "DEVFLOW_FIXTURE_DEV_SUMMARY": "Fixture sync dev",
            "DEVFLOW_FIXTURE_DEV_NOTES": "Applied sync dev changes.",
            "DEVFLOW_FIXTURE_DEV_FILES": "[\"src/sync.py\"]",
            "DEVFLOW_FIXTURE_DEV_COMMANDS": "[\"pytest tests/test_sync.py\"]",
        }
        payload = run_cli(
            "--workspace",
            str(workspace),
            "--task-id",
            "TASK-900",
            "--action",
            "dev",
            "--runtime",
            "fixture",
            env=env,
        )
        self.assertEqual(payload["next_action"], "review")
        self.assertIsNone(payload["active_subagent_role"])
        self.assertIn("Fixture sync dev", (task_dir / "dev.md").read_text(encoding="utf-8"))

    def test_load_task_context_normalizes_legacy_meta(self) -> None:
        _, workspace, task_dir = make_workspace()
        legacy_meta = {
            "task_id": "TASK-900",
            "title": "Legacy Task",
            "status": "planning",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "plan_version": 1,
            "review_round": 0,
            "current_step": "draft initial plan",
            "last_completed_step": None,
            "next_action": "update-plan",
            "is_blocked": False,
            "block_reason": None,
            "approved_at": None,
            "approved_by": None,
            "execution_mode": "manual",
            "auto_loop_state": None,
            "worktree_path": str(task_dir),
            "worktree_branch": "codex/devflow/TASK-900",
            "worktree_base_ref": "main",
            "architecture_id": None,
            "module_id": None,
            "architecture_path": None,
        }
        seed_task(task_dir, legacy_meta)

        context = load_task_context(workspace, "TASK-900")
        self.assertIn("active_subagent_role", context.meta)
        saved_meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertIn("active_subagent_role", saved_meta)


if __name__ == "__main__":
    unittest.main()
