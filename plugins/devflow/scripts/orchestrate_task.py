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

from agent_runtime import DispatchResult, ReviewVerdict, get_runtime_adapter, load_run_result
from dev_executor import append_dev_log, load_dev_result
from devflow_lib import auto_dev_next_step, auto_dev_stop_reason
from orchestrator_lib import (
    active_run_spec,
    append_plan_history,
    append_task_event,
    clear_active_subagent_fields,
    create_subagent_run,
    create_task_via_helper,
    generate_change_summary,
    load_artifact_text,
    load_task_context,
    mark_task_blocked,
    overwrite_result_payload,
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
    parser.add_argument("--planner-agent-id", help="Planner agent id to persist for compatibility fields.")
    parser.add_argument("--review-body", help="Review markdown body supplied by the host reviewer.")
    parser.add_argument("--review-file", help="File containing review markdown body.")
    parser.add_argument(
        "--review-verdict",
        choices=["pass", "changes_requested", "blocked"],
        help="Reviewer verdict for `review`.",
    )
    parser.add_argument("--approved-by", default="user", help="Approver identity for `approve-plan`.")
    parser.add_argument("--dev-summary", help="Optional development slice focus or host-supplied dev result summary.")
    parser.add_argument("--dev-notes", help="Markdown notes supplied for a completed dev result.")
    parser.add_argument("--dev-file", action="append", default=[], help="Touched file path for a completed dev result.")
    parser.add_argument("--dev-command", action="append", default=[], help="Command used during a completed dev result.")
    parser.add_argument("--history-reason", help="Reason string when appending plan history.")
    parser.add_argument("--runtime", default="unsupported", help="Runtime adapter name for planner/dev/reviewer dispatch.")
    parser.add_argument("--reviewer-agent-id", help="Reviewer agent id to persist for compatibility fields.")
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
        "active_subagent_role": context.meta.get("active_subagent_role"),
        "active_subagent_run_id": context.meta.get("active_subagent_run_id"),
        "active_subagent_name": context.meta.get("active_subagent_name"),
        "active_subagent_id": context.meta.get("active_subagent_id"),
        "active_subagent_status": context.meta.get("active_subagent_status"),
        "active_subagent_request_path": context.meta.get("active_subagent_request_path"),
        "active_subagent_result_path": context.meta.get("active_subagent_result_path"),
        "last_subagent_role": context.meta.get("last_subagent_role"),
        "last_subagent_run_id": context.meta.get("last_subagent_run_id"),
        **extra,
    }


def compat_fields_for_dispatch(context, role: str, args: argparse.Namespace, dispatch_result: DispatchResult) -> dict[str, object]:
    fields: dict[str, object] = {}
    if role == "plan":
        agent_id = args.planner_agent_id or dispatch_result.agent_id or context.meta.get("planner_agent_id")
        if agent_id:
            fields["planner_agent_id"] = agent_id
            fields["planner_agent_status"] = "live"
        fields["planner_session_resumable"] = False
    elif role == "review":
        agent_id = args.reviewer_agent_id or dispatch_result.agent_id or context.meta.get("reviewer_agent_id")
        if agent_id:
            fields["reviewer_agent_id"] = agent_id
            fields["reviewer_agent_status"] = "live"
        fields["reviewer_session_resumable"] = False
    return fields


def compat_fields_for_completion(context, role: str) -> dict[str, object]:
    fields: dict[str, object] = {}
    if role == "plan":
        if context.meta.get("planner_agent_id"):
            fields["planner_agent_status"] = "stale"
        fields["planner_session_resumable"] = False
    elif role == "review":
        if context.meta.get("reviewer_agent_id"):
            fields["reviewer_agent_status"] = "stale"
        fields["reviewer_session_resumable"] = False
    return fields


def dispatch_run(context, args: argparse.Namespace, spec) -> DispatchResult:
    return get_runtime_adapter(args.runtime).dispatch(
        role=spec.role,
        request_path=str(spec.request_path),
        context_path=str(spec.context_path),
        result_path=str(spec.result_json_path),
        task_context_minimal=context.minimal_runtime_payload(),
    )


def has_explicit_dev_result(args: argparse.Namespace) -> bool:
    return bool(args.dev_notes or args.dev_file or args.dev_command)


def direct_result_written(spec, args: argparse.Namespace) -> bool:
    if spec.role == "plan":
        plan_body = load_artifact_text(args.plan_body, args.plan_file)
        if not plan_body:
            return False
        overwrite_result_payload(spec, status="completed", summary="Plan artifact received.", body=plan_body)
        return True
    if spec.role == "review":
        review_body = load_artifact_text(args.review_body, args.review_file)
        if not review_body or not args.review_verdict:
            return False
        overwrite_result_payload(
            spec,
            status="completed",
            summary=f"Review verdict: {args.review_verdict}",
            verdict=args.review_verdict,
            body=review_body,
        )
        return True
    if spec.role == "dev":
        if not args.dev_summary or not has_explicit_dev_result(args):
            return False
        overwrite_result_payload(
            spec,
            status="completed",
            summary=args.dev_summary,
            body=args.dev_notes or "",
            files_touched=args.dev_file,
            commands=args.dev_command,
        )
        return True
    return False


def finalize_plan_run(context, args: argparse.Namespace, spec) -> dict[str, object]:
    run_result = load_run_result(spec.result_json_path)
    if run_result.status != "completed":
        raise RuntimeError(f"Plan run {spec.run_id} is not completed.")
    plan_body = spec.result_md_path.read_text(encoding="utf-8").strip()
    if not plan_body:
        raise RuntimeError(f"Plan run {spec.run_id} completed without result.md content.")

    initial_plan = "initial plan" in str(context.meta.get("current_step") or "").lower() or (
        context.meta.get("plan_version") == 1 and context.meta.get("next_action") == "update-plan"
    )
    if not initial_plan:
        reason = args.history_reason or "Plan revised through orchestrator."
        append_task_event(context.task_dir, "action.update_plan.started", {"reason": reason, "resumed": True})
        append_plan_history(context.task_dir, reason)

    write_markdown_artifact(context.task_dir, "plan.md", plan_body)
    append_task_event(context.task_dir, "artifact.plan.written", {"run_id": spec.run_id, "source": "subagent"})
    set_fields = {
        "current_step": "awaiting user approval for initial plan" if initial_plan else "awaiting user approval for revised plan",
        "last_completed_step": "initial plan drafted" if initial_plan else "plan revised",
        "next_action": "approve-plan",
        "is_blocked": False,
        "block_reason": None,
        **clear_active_subagent_fields(role="plan", run_id=spec.run_id),
        **compat_fields_for_completion(context, "plan"),
    }
    context = update_task_state(
        context,
        transition=None if initial_plan else "plan-updated",
        set_fields=set_fields,
    )
    append_task_event(
        context.task_dir,
        "action.plan.completed" if initial_plan else "action.update_plan.completed",
        {"run_id": spec.run_id, "artifact_written": True},
    )
    return build_payload(context, artifact_written=True, run_result=run_result.to_dict())


def finalize_dev_run(context, spec) -> dict[str, object]:
    dev_result = load_dev_result(spec.result_json_path, spec.result_md_path)
    if dev_result.status != "completed":
        raise RuntimeError(f"Dev run {spec.run_id} is not completed.")
    append_dev_log(
        context.task_dir,
        summary=dev_result.summary,
        notes=dev_result.notes,
        files_touched=dev_result.files_touched,
        commands=dev_result.commands,
    )
    context = update_task_state(
        context,
        set_fields={
            "current_step": "awaiting review after dev slice",
            "last_completed_step": f"dev slice completed: {dev_result.summary}",
            "next_action": dev_result.next_action,
            "is_blocked": False,
            "block_reason": None,
            **clear_active_subagent_fields(role="dev", run_id=spec.run_id),
        },
    )
    append_task_event(context.task_dir, "action.dev.completed", {"run_id": spec.run_id, **dev_result.to_dict()})
    return build_payload(context, dev_result=dev_result.to_dict())


def finalize_review_run(context, spec) -> dict[str, object]:
    run_result = load_run_result(spec.result_json_path)
    if run_result.status != "completed":
        raise RuntimeError(f"Review run {spec.run_id} is not completed.")
    review_body = spec.result_md_path.read_text(encoding="utf-8").strip()
    verdict = run_result.verdict
    if not review_body or not verdict:
        raise RuntimeError(f"Review run {spec.run_id} completed without review body or verdict.")

    write_markdown_artifact(context.task_dir, "review.md", review_body)
    append_task_event(context.task_dir, "artifact.review.written", {"run_id": spec.run_id, "verdict": verdict})

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
            **clear_active_subagent_fields(role="review", run_id=spec.run_id),
            **compat_fields_for_completion(context, "review"),
        },
    )
    append_task_event(context.task_dir, "action.review.completed", {"run_id": spec.run_id, "verdict": verdict})
    return build_payload(context, verdict=verdict, run_result=run_result.to_dict())


def maybe_finalize_active_run(
    context,
    args: argparse.Namespace,
    *,
    allow_direct_result_roles: set[str] | None = None,
) -> dict[str, object] | None:
    spec = active_run_spec(context)
    if not spec:
        return None

    if allow_direct_result_roles is None or spec.role in allow_direct_result_roles:
        direct_result_written(spec, args)
    run_result = load_run_result(spec.result_json_path)
    if run_result.status == "pending":
        return None
    if run_result.status in {"failed", "blocked"}:
        transition = "review-blocked" if spec.role == "review" else None
        blocked_fields = {
            "is_blocked": True,
            "block_reason": run_result.error or f"{spec.agent_name} run {spec.run_id} failed.",
            "current_step": f"{spec.role} run failed",
            **clear_active_subagent_fields(role=spec.role, run_id=spec.run_id),
            **compat_fields_for_completion(context, spec.role),
        }
        if context.meta.get("execution_mode") == "auto_dev":
            blocked_fields["auto_loop_state"] = "blocked"
        blocked_context = update_task_state(
            context,
            transition=transition,
            set_fields=blocked_fields,
        )
        append_task_event(
            context.task_dir,
            f"action.{spec.role}.blocked",
            {"run_id": spec.run_id, **run_result.to_dict()},
        )
        return build_payload(blocked_context, run_result=run_result.to_dict())
    if spec.role == "plan":
        return finalize_plan_run(context, args, spec)
    if spec.role == "dev":
        return finalize_dev_run(context, spec)
    if spec.role == "review":
        return finalize_review_run(context, spec)
    raise RuntimeError(f"Unknown active subagent role: {spec.role}")


def dispatch_pending_run(context, args: argparse.Namespace, spec, current_step: str, action_name: str) -> dict[str, object]:
    dispatch_result = dispatch_run(context, args, spec)
    if dispatch_result.status in {"failed", "blocked"}:
        reason = dispatch_result.error or f"{spec.agent_name} dispatch failed."
        failure_step = f"{spec.role} dispatch failed"
        if spec.role == "review":
            blocked_context = update_task_state(
                context,
                transition="review-blocked",
                set_fields={
                    "is_blocked": True,
                    "block_reason": reason,
                    "current_step": failure_step,
                    **clear_active_subagent_fields(role=spec.role, run_id=spec.run_id),
                    **compat_fields_for_completion(context, spec.role),
                },
            )
        else:
            blocked_context = mark_task_blocked(context, reason, current_step=failure_step)
        append_task_event(
            context.task_dir,
            f"action.{action_name}.blocked",
            {"run_id": spec.run_id, **dispatch_result.to_dict()},
        )
        return build_payload(blocked_context, dispatch_result=dispatch_result.to_dict())

    active_status = "completed" if load_run_result(spec.result_json_path).status == "completed" else ("dispatched" if dispatch_result.agent_id else "pending")
    context = update_task_state(
        context,
        set_fields={
            "current_step": current_step,
            "is_blocked": False,
            "block_reason": None,
            **spec.to_meta_fields(agent_id=dispatch_result.agent_id, status=active_status),
            **compat_fields_for_dispatch(context, spec.role, args, dispatch_result),
        },
    )
    append_task_event(
        context.task_dir,
        f"action.{action_name}.dispatched",
        {"run_id": spec.run_id, **dispatch_result.to_dict()},
    )

    finalized = maybe_finalize_active_run(
        context,
        args,
        allow_direct_result_roles={"plan", "review"},
    )
    if finalized is not None:
        return finalized
    return build_payload(
        context,
        dispatch_result=dispatch_result.to_dict(),
        run_id=spec.run_id,
        request_path=str(spec.request_path),
        context_path=str(spec.context_path),
        result_path=str(spec.result_json_path),
    )


def dispatch_plan_run(context, args: argparse.Namespace, *, initial_plan: bool) -> dict[str, object]:
    spec = create_subagent_run(context, "plan")
    append_task_event(context.task_dir, "action.plan.handoff_created" if initial_plan else "action.update_plan.handoff_created", {"run_id": spec.run_id})
    if direct_result_written(spec, args):
        context = update_task_state(
            context,
            set_fields=spec.to_meta_fields(status="completed"),
        )
        return finalize_plan_run(context, args, spec)
    current_step = "awaiting planner result for initial plan" if initial_plan else "awaiting planner result for revised plan"
    return dispatch_pending_run(context, args, spec, current_step=current_step, action_name="plan" if initial_plan else "update_plan")


def dispatch_dev_run(context, args: argparse.Namespace) -> dict[str, object]:
    spec = create_subagent_run(context, "dev", focus=args.dev_summary)
    append_task_event(context.task_dir, "action.dev.handoff_created", {"run_id": spec.run_id})
    return dispatch_pending_run(context, args, spec, current_step="awaiting dev result", action_name="dev")


def dispatch_review_run(context, args: argparse.Namespace) -> dict[str, object]:
    spec = create_subagent_run(context, "review")
    append_task_event(context.task_dir, "action.review.handoff_created", {"run_id": spec.run_id})
    if direct_result_written(spec, args):
        context = update_task_state(
            context,
            set_fields=spec.to_meta_fields(status="completed"),
        )
        return finalize_review_run(context, spec)
    return dispatch_pending_run(context, args, spec, current_step="awaiting reviewer result", action_name="review")


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
    payload = dispatch_plan_run(context, args, initial_plan=True)
    payload["created"] = True
    return payload


def run_update_plan(args: argparse.Namespace) -> dict[str, object]:
    context = load_task_context(Path(args.workspace).resolve(), args.task_id)
    require_action_allowed(context, "update-plan")
    append_task_event(context.task_dir, "action.update_plan.started", {"reason": args.history_reason})
    context = update_task_state(
        context,
        set_fields={
            "status": "planning",
            "next_action": "update-plan",
            "current_step": "draft revised plan handoff",
            "approved_at": None,
            "approved_by": None,
            "execution_mode": "manual",
            "auto_loop_state": None,
            "is_blocked": False,
            "block_reason": None,
            **clear_active_subagent_fields(),
        },
    )
    return dispatch_plan_run(context, args, initial_plan=False)


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
    if context.meta.get("active_subagent_role") == "dev":
        finalized = maybe_finalize_active_run(context, args, allow_direct_result_roles={"dev"})
        if finalized is not None:
            return finalized
        spec = active_run_spec(context)
        if spec is None:
            raise RuntimeError("Active dev run metadata is incomplete.")
        return dispatch_pending_run(context, args, spec, current_step="awaiting dev result", action_name="dev")

    append_task_event(context.task_dir, "action.dev.started", {"focus": args.dev_summary})
    context = update_task_state(
        context,
        transition="dev-started",
        set_fields={
            "current_step": "draft dev handoff",
            "is_blocked": False,
            "block_reason": None,
            **clear_active_subagent_fields(),
        },
    )
    return dispatch_dev_run(context, args)


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
    context = load_task_context(Path(args.workspace).resolve(), args.task_id)
    next_step = auto_dev_next_step(context.meta)
    if next_step == "dev":
        payload = run_dev(args)
        payload["activation"] = activation
        return payload
    if next_step == "review":
        payload = run_review(args)
        payload["activation"] = activation
        return payload
    return build_payload(context, activation=activation, should_continue=next_step is not None)


def run_review(args: argparse.Namespace) -> dict[str, object]:
    context = load_task_context(Path(args.workspace).resolve(), args.task_id)
    require_action_allowed(context, "review")
    if context.meta.get("active_subagent_role") == "review":
        finalized = maybe_finalize_active_run(context, args)
        if finalized is not None:
            return finalized
        spec = active_run_spec(context)
        if spec is None:
            raise RuntimeError("Active review run metadata is incomplete.")
        return dispatch_pending_run(context, args, spec, current_step="awaiting reviewer result", action_name="review")

    append_task_event(context.task_dir, "action.review.started", {})
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

    context = update_task_state(
        context,
        transition="review-started",
        set_fields={
            "current_step": "draft review handoff",
            "is_blocked": False,
            "block_reason": None,
            **clear_active_subagent_fields(),
        },
    )
    return dispatch_review_run(context, args)


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
            **clear_active_subagent_fields(),
        },
    )
    append_task_event(context.task_dir, "action.done.completed", {})
    return build_payload(context)


def maybe_resume_blocked_execution(context, args: argparse.Namespace) -> dict[str, object] | None:
    if not context.meta.get("is_blocked") or context.meta.get("active_subagent_role"):
        return None

    next_action = context.meta.get("next_action")
    if context.meta.get("status") != "developing" or next_action not in {"dev", "review"}:
        return None
    if next_action == "review" and context.meta.get("current_step") == "task blocked by review":
        return None

    set_fields: dict[str, object] = {
        "is_blocked": False,
        "block_reason": None,
    }
    if context.meta.get("execution_mode") == "auto_dev" and context.meta.get("auto_loop_state") == "blocked":
        set_fields["auto_loop_state"] = "running"
    context = update_task_state(context, set_fields=set_fields)
    append_task_event(context.task_dir, "action.resume.redispatch", {"target": next_action})

    if next_action == "dev":
        return run_dev(args)
    return run_review(args)


def run_resume(args: argparse.Namespace) -> dict[str, object]:
    context = load_task_context(Path(args.workspace).resolve(), args.task_id)
    append_task_event(context.task_dir, "action.resume.inspected", {})

    finalized = maybe_finalize_active_run(
        context,
        args,
        allow_direct_result_roles={"plan", "dev", "review"},
    )
    if finalized is not None:
        return finalized

    resumed_blocked = maybe_resume_blocked_execution(context, args)
    if resumed_blocked is not None:
        return resumed_blocked

    spec = active_run_spec(context)
    if spec is not None:
        append_task_event(context.task_dir, "action.resume.dispatch", {"target": spec.role, "run_id": spec.run_id})
        current_step = {
            "plan": "awaiting planner result for initial plan"
            if "initial plan" in str(context.meta.get("current_step") or "").lower()
            else "awaiting planner result for revised plan",
            "dev": "awaiting dev result",
            "review": "awaiting reviewer result",
        }[spec.role]
        action_name = "plan" if spec.role == "plan" and context.meta.get("plan_version") == 1 else spec.role
        if spec.role == "plan" and context.meta.get("plan_version") != 1:
            action_name = "update_plan"
        return dispatch_pending_run(context, args, spec, current_step=current_step, action_name=action_name)

    resumable_step = auto_dev_next_step(context.meta)
    if context.meta.get("status") == "planning" and context.meta.get("next_action") == "update-plan":
        append_task_event(context.task_dir, "action.resume.dispatch", {"target": "planning"})
        return dispatch_plan_run(context, args, initial_plan=context.meta.get("plan_version") == 1)
    if resumable_step == "dev":
        append_task_event(context.task_dir, "action.resume.dispatch", {"target": "dev"})
        return run_dev(args)
    if resumable_step == "review":
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
