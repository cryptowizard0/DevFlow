#!/usr/bin/env python3
"""Deterministic task-orchestration entrypoint for DevFlow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from agent_runtime import ReviewVerdict, get_runtime_adapter
from dev_executor import run_dev_slice
from devflow_lib import auto_dev_next_step, auto_dev_stop_reason
from orchestrator_lib import (
    append_plan_history,
    append_task_event,
    create_task_via_helper,
    generate_change_summary,
    load_artifact_text,
    load_task_context,
    mark_task_blocked,
    require_action_allowed,
    update_task_state,
    write_markdown_artifact,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coordinate deterministic DevFlow task actions.")
    parser.add_argument("--workspace", required=True, help="Path to DevFlowWorkspace")
    parser.add_argument(
        "--action",
        required=True,
        choices=["plan", "update-plan", "approve-plan", "dev", "auto-dev", "review", "done", "resume"],
        help="Task action to run",
    )
    parser.add_argument("--task-id", help="Target task id. Defaults to the focus task for non-plan actions.")
    parser.add_argument("--title", help="Task title for `plan`.")
    parser.add_argument("--request", help="Task request text for `plan`.")
    parser.add_argument("--architecture-id", help="Optional architecture binding for `plan`.")
    parser.add_argument("--module-id", help="Optional module binding for `plan`.")
    parser.add_argument("--plan-body", help="Plan markdown body supplied by the host planner.")
    parser.add_argument("--plan-file", help="File containing plan markdown body.")
    parser.add_argument("--planner-agent-id", help="Planner agent id to persist during planning.")
    parser.add_argument("--planner-session-resumable", action="store_true", help="Mark the planner session as resumable.")
    parser.add_argument("--review-body", help="Review markdown body supplied by the host reviewer.")
    parser.add_argument("--review-file", help="File containing review markdown body.")
    parser.add_argument(
        "--review-verdict",
        choices=["pass", "changes_requested", "blocked"],
        help="Reviewer verdict for `review`.",
    )
    parser.add_argument("--approved-by", default="user", help="Approver identity for `approve-plan`.")
    parser.add_argument("--dev-summary", help="Short summary of the dev slice.")
    parser.add_argument("--dev-notes", help="Markdown notes to append to dev.md.")
    parser.add_argument("--dev-file", action="append", default=[], help="Touched file path for the dev slice.")
    parser.add_argument("--dev-command", action="append", default=[], help="Command used during the dev slice.")
    parser.add_argument("--history-reason", help="Reason string when appending plan history.")
    parser.add_argument("--runtime", default="unsupported", help="Runtime adapter name for planner/reviewer requests.")
    parser.add_argument("--reviewer-agent-id", help="Reviewer agent id to persist during `review`.")
    parser.add_argument("--reviewer-session-resumable", action="store_true", help="Mark the reviewer session as resumable.")
    return parser.parse_args()


def build_payload(context, **extra: object) -> dict[str, object]:
    return {
        "ok": True,
        "task_id": context.task_id,
        "status": context.meta.get("status"),
        "next_action": context.meta.get("next_action"),
        "execution_mode": context.meta.get("execution_mode"),
        "auto_loop_state": context.meta.get("auto_loop_state"),
        "auto_dev_next_step": auto_dev_next_step(context.meta),
        "auto_dev_stop_reason": auto_dev_stop_reason(context.meta),
        **extra,
    }


def planner_state_fields(args: argparse.Namespace, runtime_result=None, *, stale: bool, existing_agent_id: str | None = None) -> dict[str, object]:
    agent_id = args.planner_agent_id or (runtime_result.agent_id if runtime_result else None) or existing_agent_id
    resumable = args.planner_session_resumable or bool(getattr(runtime_result, "session_resumable", False))
    fields: dict[str, object] = {
        "planner_session_resumable": False if stale else resumable,
    }
    if agent_id:
        fields["planner_agent_id"] = agent_id
        fields["planner_agent_status"] = "stale" if stale else "live"
    return fields


def reviewer_state_fields(args: argparse.Namespace, runtime_result=None, *, stale: bool, existing_agent_id: str | None = None) -> dict[str, object]:
    agent_id = args.reviewer_agent_id or (runtime_result.agent_id if runtime_result else None) or existing_agent_id
    resumable = args.reviewer_session_resumable or bool(getattr(runtime_result, "session_resumable", False))
    fields: dict[str, object] = {
        "reviewer_session_resumable": False if stale else resumable,
    }
    if agent_id:
        fields["reviewer_agent_id"] = agent_id
        fields["reviewer_agent_status"] = "stale" if stale else "live"
    return fields


def finalize_plan_artifact(
    context,
    args: argparse.Namespace,
    plan_body: str,
    *,
    transition: str | None,
    current_step: str,
    last_completed_step: str,
    runtime_result=None,
) -> dict[str, object]:
    write_markdown_artifact(context.task_dir, "plan.md", plan_body)
    append_task_event(context.task_dir, "artifact.plan.written", {"source": "host"})
    set_fields = {
        "current_step": current_step,
        "last_completed_step": last_completed_step,
        "next_action": "approve-plan",
        "is_blocked": False,
        "block_reason": None,
        **planner_state_fields(args, runtime_result, stale=True, existing_agent_id=context.meta.get("planner_agent_id")),
    }
    context = update_task_state(context, transition=transition, set_fields=set_fields)
    return build_payload(context, artifact_written=True)


def finalize_review_result(context, args: argparse.Namespace, review_body: str, verdict: ReviewVerdict) -> dict[str, object]:
    write_markdown_artifact(context.task_dir, "review.md", review_body)
    append_task_event(context.task_dir, "artifact.review.written", {"verdict": verdict})

    transition_map: dict[ReviewVerdict, str] = {
        "pass": "review-pass",
        "changes_requested": "review-changes-requested",
        "blocked": "review-blocked",
    }
    completion_steps = {
        "pass": "review passed",
        "changes_requested": "review requested changes",
        "blocked": "review blocked",
    }
    next_steps = {
        "pass": "awaiting explicit done action",
        "changes_requested": "awaiting next dev slice after review",
        "blocked": "task blocked by review",
    }
    context = update_task_state(
        context,
        transition=transition_map[verdict],
        set_fields={
            "current_step": next_steps[verdict],
            "last_completed_step": completion_steps[verdict],
            **reviewer_state_fields(args, stale=True, existing_agent_id=context.meta.get("reviewer_agent_id")),
        },
    )
    append_task_event(context.task_dir, "action.review.completed", {"verdict": verdict})
    return build_payload(context, verdict=verdict)


def continue_review_runtime(context, args: argparse.Namespace) -> dict[str, object]:
    review_body = load_artifact_text(args.review_body, args.review_file)
    verdict = args.review_verdict
    runtime_result = None
    if not review_body or not verdict:
        runtime_result = get_runtime_adapter(args.runtime).request_review(context.to_runtime_payload())
        if runtime_result.status == "completed" and runtime_result.artifact_body and runtime_result.verdict:
            review_body = runtime_result.artifact_body
            verdict = runtime_result.verdict
        elif runtime_result.agent_id and runtime_result.session_resumable:
            context = update_task_state(
                context,
                set_fields={
                    "current_step": "awaiting reviewer result",
                    **reviewer_state_fields(args, runtime_result, stale=False, existing_agent_id=context.meta.get("reviewer_agent_id")),
                },
            )
            append_task_event(context.task_dir, "action.review.resumed", runtime_result.to_dict())
            return build_payload(context, reviewer_result=runtime_result.to_dict(), resumable_step="review")
        else:
            context = update_task_state(
                context,
                set_fields={
                    "status": "developing",
                    "next_action": "review",
                    "current_step": "reviewer unavailable while waiting for verdict",
                    "is_blocked": True,
                    "block_reason": runtime_result.error or "Reviewer runtime did not return an artifact and verdict.",
                    "auto_loop_state": "blocked" if context.meta.get("execution_mode") == "auto_dev" else context.meta.get("auto_loop_state"),
                    **reviewer_state_fields(args, runtime_result, stale=False, existing_agent_id=context.meta.get("reviewer_agent_id")),
                },
            )
            append_task_event(context.task_dir, "action.review.blocked", runtime_result.to_dict())
            return build_payload(context, verdict="blocked", reviewer_result=runtime_result.to_dict())

    return finalize_review_result(context, args, review_body, verdict)


def continue_planner_runtime(context, args: argparse.Namespace, *, initial_plan: bool) -> dict[str, object]:
    plan_body = load_artifact_text(args.plan_body, args.plan_file)
    runtime_result = None
    if not plan_body:
        runtime_result = get_runtime_adapter(args.runtime).request_plan(context.to_runtime_payload())
        if runtime_result.status == "completed" and runtime_result.artifact_body:
            plan_body = runtime_result.artifact_body
        elif runtime_result.agent_id and runtime_result.session_resumable:
            wait_step = "awaiting planner result for initial plan" if initial_plan else "awaiting planner result for revised plan"
            context = update_task_state(
                context,
                set_fields={
                    "current_step": wait_step,
                    "is_blocked": False,
                    "block_reason": None,
                    **planner_state_fields(args, runtime_result, stale=False, existing_agent_id=context.meta.get("planner_agent_id")),
                },
            )
            append_task_event(context.task_dir, "action.plan.resumed", runtime_result.to_dict())
            return build_payload(context, planner_result=runtime_result.to_dict())
        else:
            block_step = "planner unavailable while creating task plan" if initial_plan else "planner unavailable while revising plan"
            context = update_task_state(
                context,
                set_fields={
                    "current_step": block_step,
                    "is_blocked": True,
                    "block_reason": runtime_result.error or "Planner runtime did not return a plan artifact.",
                    "auto_loop_state": "blocked" if context.meta.get("execution_mode") == "auto_dev" else context.meta.get("auto_loop_state"),
                    **planner_state_fields(args, runtime_result, stale=False, existing_agent_id=context.meta.get("planner_agent_id")),
                },
            )
            append_task_event(context.task_dir, "action.plan.blocked", runtime_result.to_dict())
            return build_payload(context, planner_result=runtime_result.to_dict())

    if initial_plan:
        return finalize_plan_artifact(
            context,
            args,
            plan_body,
            transition=None,
            current_step="awaiting user approval for initial plan",
            last_completed_step="initial plan drafted",
            runtime_result=runtime_result,
        )

    reason = args.history_reason or "Plan revised through orchestrator."
    append_task_event(context.task_dir, "action.update_plan.started", {"reason": reason, "resumed": True})
    append_plan_history(context.task_dir, reason)
    payload = finalize_plan_artifact(
        context,
        args,
        plan_body,
        transition="plan-updated",
        current_step="awaiting user approval for revised plan",
        last_completed_step="plan revised",
        runtime_result=runtime_result,
    )
    append_task_event(context.task_dir, "action.update_plan.completed", {"resumed": True})
    return payload


def run_plan(args: argparse.Namespace) -> dict[str, object]:
    if not args.title or not args.request:
        raise RuntimeError("`plan` requires --title and --request.")

    created = create_task_via_helper(
        workspace=Path(args.workspace).resolve(),
        title=args.title,
        request_text=args.request,
        architecture_id=args.architecture_id,
        module_id=args.module_id,
    )
    context = load_task_context(Path(args.workspace).resolve(), created["task_id"])
    append_task_event(context.task_dir, "action.plan.started", {"title": args.title})

    plan_body = load_artifact_text(args.plan_body, args.plan_file)
    if not plan_body:
        runtime_result = get_runtime_adapter(args.runtime).request_plan(context.to_runtime_payload())
        if runtime_result.status == "completed" and runtime_result.artifact_body:
            plan_body = runtime_result.artifact_body
        else:
            if runtime_result.agent_id and runtime_result.session_resumable:
                context = update_task_state(
                    context,
                    set_fields={
                        "current_step": "awaiting planner result for initial plan",
                        "is_blocked": False,
                        "block_reason": None,
                        **planner_state_fields(args, runtime_result, stale=False, existing_agent_id=context.meta.get("planner_agent_id")),
                    },
                )
                append_task_event(context.task_dir, "action.plan.resumed", runtime_result.to_dict())
                return build_payload(context, created=True, artifact_written=False, planner_result=runtime_result.to_dict())
            context = mark_task_blocked(
                context,
                runtime_result.error or "Planner runtime did not return a plan artifact.",
                current_step="planner unavailable while creating task plan",
            )
            append_task_event(context.task_dir, "action.plan.blocked", runtime_result.to_dict())
            return build_payload(context, created=True, artifact_written=False, planner_result=runtime_result.to_dict())

    if plan_body:
        payload = finalize_plan_artifact(
            context,
            args,
            plan_body,
            transition=None,
            current_step="awaiting user approval for initial plan",
            last_completed_step="initial plan drafted",
            runtime_result=runtime_result if "runtime_result" in locals() else None,
        )
        append_task_event(context.task_dir, "action.plan.completed", {"artifact_written": True})
        payload["created"] = True
        return payload

    append_task_event(context.task_dir, "action.plan.completed", {"artifact_written": False})
    return build_payload(context, created=True, artifact_written=False, artifact_required="plan")


def run_update_plan(args: argparse.Namespace) -> dict[str, object]:
    context = load_task_context(Path(args.workspace).resolve(), args.task_id)
    require_action_allowed(context, "update-plan")
    plan_body = load_artifact_text(args.plan_body, args.plan_file)
    if not plan_body:
        runtime_result = get_runtime_adapter(args.runtime).request_plan(context.to_runtime_payload())
        if runtime_result.status == "completed" and runtime_result.artifact_body:
            plan_body = runtime_result.artifact_body
        else:
            if runtime_result.agent_id and runtime_result.session_resumable:
                context = update_task_state(
                    context,
                    set_fields={
                        "status": "planning",
                        "next_action": "update-plan",
                        "current_step": "awaiting planner result for revised plan",
                        "approved_at": None,
                        "approved_by": None,
                        "execution_mode": "manual",
                        "auto_loop_state": None,
                        "is_blocked": False,
                        "block_reason": None,
                        **planner_state_fields(args, runtime_result, stale=False),
                    },
                )
                append_task_event(context.task_dir, "action.update_plan.resumed", runtime_result.to_dict())
                return build_payload(context, planner_result=runtime_result.to_dict())
            context = mark_task_blocked(
                context,
                runtime_result.error or "Planner runtime did not return a revised plan artifact.",
                current_step="planner unavailable while revising plan",
            )
            append_task_event(context.task_dir, "action.update_plan.blocked", runtime_result.to_dict())
            return build_payload(context, planner_result=runtime_result.to_dict())

    reason = args.history_reason or "Plan revised through orchestrator."
    append_task_event(context.task_dir, "action.update_plan.started", {"reason": reason})
    append_plan_history(context.task_dir, reason)
    payload = finalize_plan_artifact(
        context,
        args,
        plan_body,
        transition="plan-updated",
        current_step="awaiting user approval for revised plan",
        last_completed_step="plan revised",
        runtime_result=runtime_result if "runtime_result" in locals() else None,
    )
    context = load_task_context(Path(args.workspace).resolve(), args.task_id)
    append_task_event(context.task_dir, "action.update_plan.completed", {"plan_version": context.meta.get("plan_version")})
    return payload


def run_approve_plan(args: argparse.Namespace) -> dict[str, object]:
    context = load_task_context(Path(args.workspace).resolve(), args.task_id)
    require_action_allowed(context, "approve-plan")
    append_task_event(context.task_dir, "action.approve_plan.started", {"approved_by": args.approved_by})
    context = update_task_state(
        context,
        transition="plan-approved",
        set_fields={
            "approved_by": args.approved_by,
            "current_step": "plan approved; ready for development",
            "last_completed_step": "plan approved",
        },
    )
    append_task_event(context.task_dir, "action.approve_plan.completed", {"approved_by": args.approved_by})
    return build_payload(context)


def run_dev(args: argparse.Namespace) -> dict[str, object]:
    context = load_task_context(Path(args.workspace).resolve(), args.task_id)
    require_action_allowed(context, "dev")
    append_task_event(context.task_dir, "action.dev.started", {"summary": args.dev_summary})
    context = update_task_state(
        context,
        transition="dev-started",
        set_fields={"current_step": "executing dev slice"},
    )

    result = run_dev_slice(
        context.task_dir,
        summary=args.dev_summary or "",
        notes=args.dev_notes,
        files_touched=args.dev_file,
        commands=args.dev_command,
    )
    if result.status != "completed":
        context = mark_task_blocked(context, result.error or "Unknown dev execution failure.", current_step="dev slice failed")
        append_task_event(context.task_dir, "action.dev.blocked", result.to_dict())
        return build_payload(context, dev_result=result.to_dict())

    context = update_task_state(
        context,
        set_fields={
            "current_step": "awaiting review after dev slice",
            "last_completed_step": f"dev slice completed: {result.summary}",
            "next_action": result.next_action,
        },
    )
    append_task_event(context.task_dir, "action.dev.completed", result.to_dict())
    return build_payload(context, dev_result=result.to_dict())


def run_auto_dev(args: argparse.Namespace) -> dict[str, object]:
    context = load_task_context(Path(args.workspace).resolve(), args.task_id)
    require_action_allowed(context, "auto-dev")
    activation = "already_running"
    if context.meta.get("execution_mode") != "auto_dev" or context.meta.get("auto_loop_state") != "running":
        context = update_task_state(
            context,
            set_fields={
                "execution_mode": "auto_dev",
                "auto_loop_state": "running",
                "current_step": "auto-dev running",
            },
        )
        activation = "started"
    append_task_event(context.task_dir, "action.auto_dev.started", {"activation": activation})
    return build_payload(context, activation=activation, should_continue=auto_dev_next_step(context.meta) is not None)


def run_review(args: argparse.Namespace) -> dict[str, object]:
    context = load_task_context(Path(args.workspace).resolve(), args.task_id)
    require_action_allowed(context, "review")
    append_task_event(context.task_dir, "action.review.started", {})
    context = update_task_state(
        context,
        transition="review-started",
        set_fields={
            "current_step": "awaiting reviewer result",
            "reviewer_agent_id": args.reviewer_agent_id,
        },
    )
    try:
        generate_change_summary(context.task_dir, repo_root=context.repo_root)
    except Exception as exc:
        context = update_task_state(
            context,
            set_fields={
                "status": "developing",
                "next_action": "review",
                "current_step": "blocked while generating change summary",
                "is_blocked": True,
                "block_reason": str(exc),
                "auto_loop_state": "blocked" if context.meta.get("execution_mode") == "auto_dev" else context.meta.get("auto_loop_state"),
            },
        )
        append_task_event(context.task_dir, "action.review.blocked", {"error": str(exc)})
        return build_payload(context, verdict="blocked", error=str(exc))

    review_body = load_artifact_text(args.review_body, args.review_file)
    verdict = args.review_verdict
    if not review_body or not verdict:
        runtime_result = get_runtime_adapter(args.runtime).request_review(context.to_runtime_payload())
        if runtime_result.status == "completed" and runtime_result.artifact_body and runtime_result.verdict:
            review_body = runtime_result.artifact_body
            verdict = runtime_result.verdict
        elif runtime_result.agent_id and runtime_result.session_resumable:
            context = update_task_state(
                context,
                set_fields={
                    "current_step": "awaiting reviewer result",
                    **reviewer_state_fields(args, runtime_result, stale=False),
                },
            )
            append_task_event(context.task_dir, "action.review.resumed", runtime_result.to_dict())
            return build_payload(context, reviewer_result=runtime_result.to_dict(), resumable_step="review")
        else:
            context = update_task_state(
                context,
                set_fields={
                    "status": "developing",
                    "next_action": "review",
                    "current_step": "reviewer unavailable while waiting for verdict",
                    "is_blocked": True,
                    "block_reason": runtime_result.error or "Reviewer runtime did not return an artifact and verdict.",
                    "auto_loop_state": "blocked" if context.meta.get("execution_mode") == "auto_dev" else context.meta.get("auto_loop_state"),
                    **reviewer_state_fields(args, runtime_result, stale=False),
                },
            )
            append_task_event(context.task_dir, "action.review.blocked", runtime_result.to_dict())
            return build_payload(context, verdict="blocked", reviewer_result=runtime_result.to_dict())

    return finalize_review_result(context, args, review_body, verdict)


def run_done(args: argparse.Namespace) -> dict[str, object]:
    context = load_task_context(Path(args.workspace).resolve(), args.task_id)
    require_action_allowed(context, "done")
    append_task_event(context.task_dir, "action.done.started", {})
    context = update_task_state(
        context,
        transition="task-done",
        set_fields={
            "current_step": "task complete",
            "last_completed_step": "task done",
        },
    )
    append_task_event(context.task_dir, "action.done.completed", {})
    return build_payload(context)


def run_resume(args: argparse.Namespace) -> dict[str, object]:
    context = load_task_context(Path(args.workspace).resolve(), args.task_id)
    append_task_event(context.task_dir, "action.resume.inspected", {})
    resumable_step = auto_dev_next_step(context.meta)
    current_step = str(context.meta.get("current_step") or "").lower()
    awaiting_planner = "awaiting planner result" in current_step
    planning_pending = context.meta.get("status") == "planning" and context.meta.get("next_action") == "update-plan"
    has_plan_input = bool(args.plan_body or args.plan_file)
    has_review_input = bool(args.review_body or args.review_file or args.review_verdict)
    has_dev_input = bool(args.dev_summary)

    if (planning_pending or awaiting_planner) and (has_plan_input or context.meta.get("planner_session_resumable") or args.runtime != "unsupported"):
        append_task_event(context.task_dir, "action.resume.dispatch", {"target": "planning"})
        initial_plan = "initial plan" in str(context.meta.get("current_step") or "").lower() or context.meta.get("plan_version") == 1
        return continue_planner_runtime(context, args, initial_plan=initial_plan)
    if context.meta.get("status") == "reviewing" and (has_review_input or context.meta.get("reviewer_session_resumable") or args.runtime != "unsupported"):
        append_task_event(context.task_dir, "action.resume.dispatch", {"target": "review"})
        return continue_review_runtime(context, args)
    if resumable_step == "dev" and has_dev_input:
        append_task_event(context.task_dir, "action.resume.dispatch", {"target": "dev"})
        return run_dev(args)
    if resumable_step == "review" and (has_review_input or context.meta.get("reviewer_session_resumable") or args.runtime != "unsupported"):
        append_task_event(context.task_dir, "action.resume.dispatch", {"target": "review"})
        return run_review(args)
    return build_payload(
        context,
        should_continue=resumable_step is not None,
        resumable_step=resumable_step,
    )


def main() -> int:
    args = parse_args()
    action_handlers = {
        "plan": run_plan,
        "update-plan": run_update_plan,
        "approve-plan": run_approve_plan,
        "dev": run_dev,
        "auto-dev": run_auto_dev,
        "review": run_review,
        "done": run_done,
        "resume": run_resume,
    }
    try:
        payload = action_handlers[args.action](args)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        failure = {
            "ok": False,
            "action": args.action,
            "error": str(exc),
        }
        print(json.dumps(failure, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
