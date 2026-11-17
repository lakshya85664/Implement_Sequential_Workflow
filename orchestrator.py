
"""Task 2 - Sequential employee onboarding workflow."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from sequential_workflow import (
    EmployeeOnboardingInput,
    TaskResult,
    TaskStatus,
    WorkflowRun,
    WorkflowState,
    create_onboarding_tasks,
    transition,
)


ROOT = Path(__file__).resolve().parent
MAX_TASKS_PER_RUN = 4


class WorkflowExecutionError(Exception):
    """Raised when a sequential workflow cannot safely continue."""


class SequentialOnboardingWorkflow:
    """Executes onboarding tasks in order with explicit context handoff."""

    def __init__(
        self,
        max_tasks: int = MAX_TASKS_PER_RUN,
        task_handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] | None = None,
    ):
        if max_tasks < 1:
            raise ValueError("max_tasks must be at least 1")

        self.max_tasks = max_tasks
        self.task_handlers = task_handlers or {
            "create_employee_account": self._create_account,
            "assign_equipment": self._assign_equipment,
            "schedule_orientation": self._schedule_orientation,
            "notify_manager": self._notify_manager,
        }

    @staticmethod
    def _create_account(context: dict[str, Any]) -> dict[str, Any]:
        employee = context["employee"]
        return {
            "account_id": f"ACC-{employee['employee_id']}",
            "username": employee["email"].split("@")[0],
            "account_status": "created",
        }

    @staticmethod
    def _assign_equipment(context: dict[str, Any]) -> dict[str, Any]:
        employee = context["employee"]
        account = context["account"]

        if account.get("account_status") != "created":
            raise WorkflowExecutionError(
                "Equipment assignment requires a created employee account"
            )

        return {
            "assignment_id": f"EQ-{employee['employee_id']}",
            "equipment_type": employee["equipment_type"],
            "assignment_status": "assigned",
            "account_id": account["account_id"],
        }

    @staticmethod
    def _schedule_orientation(context: dict[str, Any]) -> dict[str, Any]:
        employee = context["employee"]
        equipment = context["equipment"]

        if equipment.get("assignment_status") != "assigned":
            raise WorkflowExecutionError(
                "Orientation requires completed equipment assignment"
            )

        return {
            "orientation_id": f"ORI-{employee['employee_id']}",
            "schedule": "Next business day at 10:00",
            "department": employee["department"],
            "orientation_status": "scheduled",
        }

    @staticmethod
    def _notify_manager(context: dict[str, Any]) -> dict[str, Any]:
        employee = context["employee"]
        orientation = context["orientation"]

        if orientation.get("orientation_status") != "scheduled":
            raise WorkflowExecutionError(
                "Manager notification requires scheduled orientation"
            )

        return {
            "recipient": employee["manager_email"],
            "employee_id": employee["employee_id"],
            "notification_status": "sent",
            "orientation_id": orientation["orientation_id"],
        }

    @staticmethod
    def _validate_employee(
        employee: EmployeeOnboardingInput | dict[str, Any],
    ) -> EmployeeOnboardingInput:
        if isinstance(employee, EmployeeOnboardingInput):
            return employee

        return EmployeeOnboardingInput.model_validate(employee)

    def execute(
        self,
        employee: EmployeeOnboardingInput | dict[str, Any],
        run_id: str = "RUN-ONBOARD-2001",
    ) -> WorkflowRun:
        """Execute all onboarding tasks in strict sequence."""

        try:
            validated_employee = self._validate_employee(employee)
        except ValidationError as exc:
            raise WorkflowExecutionError(
                f"Employee input validation failed: {exc}"
            ) from exc

        tasks = create_onboarding_tasks()

        if len(tasks) > self.max_tasks:
            raise WorkflowExecutionError(
                f"Workflow task limit exceeded: {len(tasks)} > {self.max_tasks}"
            )

        run = WorkflowRun(
            run_id=run_id,
            business_key=validated_employee.employee_id,
            context={"employee": validated_employee.model_dump()},
            tasks=tasks,
        )

        transition(run, "start")
        run.record_event(
            "onboarding.execution_started",
            employee_id=validated_employee.employee_id,
            task_count=len(tasks),
        )

        completed_task_ids: set[str] = set()

        for task in tasks:
            if task.sequence > self.max_tasks:
                raise WorkflowExecutionError("Maximum task count reached")

            if task.dependency and task.dependency not in completed_task_ids:
                task.status = TaskStatus.SKIPPED
                run.record_event(
                    "task.dependency_blocked",
                    task_id=task.task_id,
                    dependency=task.dependency,
                )
                raise WorkflowExecutionError(
                    f"Dependency {task.dependency} not completed for {task.name}"
                )

            handler = self.task_handlers.get(task.name)
            if handler is None:
                task.status = TaskStatus.FAILED
                raise WorkflowExecutionError(
                    f"No handler registered for task: {task.name}"
                )

            task.status = TaskStatus.RUNNING
            task.attempts += 1
            run.record_event(
                "task.started",
                task_id=task.task_id,
                task_name=task.name,
                sequence=task.sequence,
                owner=task.owner,
            )
            run.record_trace(
                event="task.started",
                task_id=task.task_id,
                outcome="started",
                next_action=task.name,
            )

            try:
                output = handler(run.context)

                if not isinstance(output, dict) or not output:
                    raise WorkflowExecutionError(
                        f"Task {task.name} returned an invalid result"
                    )

                # Explicit handoff: each task's output is stored in context.
                context_key = {
                    "create_employee_account": "account",
                    "assign_equipment": "equipment",
                    "schedule_orientation": "orientation",
                    "notify_manager": "notification",
                }[task.name]

                run.context[context_key] = output
                task.result = output
                task.status = TaskStatus.COMPLETED
                completed_task_ids.add(task.task_id)

                completed_at = datetime.now(timezone.utc).isoformat()
                result = TaskResult(
                    task_id=task.task_id,
                    task_name=task.name,
                    status=task.status.value,
                    output=output,
                    completed_at=completed_at,
                )
                run.results.append(result)

                run.record_event(
                    "task.completed",
                    task_id=task.task_id,
                    task_name=task.name,
                    output=output,
                )
                run.record_trace(
                    event="task.completed",
                    task_id=task.task_id,
                    outcome="completed",
                    next_action="next_task" if task.sequence < len(tasks) else "complete_workflow",
                )

            except Exception as exc:
                task.status = TaskStatus.FAILED
                run.record_event(
                    "task.failed",
                    task_id=task.task_id,
                    task_name=task.name,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                run.record_trace(
                    event="task.failed",
                    task_id=task.task_id,
                    outcome="failed",
                    next_action="operator_review",
                )

                if run.state == WorkflowState.RUNNING:
                    transition(run, "fail")

                # Do not execute downstream tasks after a failure.
                for remaining in tasks:
                    if remaining.status == TaskStatus.PENDING:
                        remaining.status = TaskStatus.SKIPPED

                raise WorkflowExecutionError(
                    f"Workflow failed at task {task.name}: {exc}"
                ) from exc

        transition(run, "complete")
        run.record_event(
            "onboarding.execution_completed",
            employee_id=validated_employee.employee_id,
            completed_tasks=len(run.results),
        )

        return run


def serialize_run(run: WorkflowRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "business_key": run.business_key,
        "state": run.state.value,
        "context": run.context,
        "tasks": [
            {
                "task_id": task.task_id,
                "name": task.name,
                "sequence": task.sequence,
                "dependency": task.dependency,
                "owner": task.owner,
                "status": task.status.value,
                "attempts": task.attempts,
                "result": task.result,
            }
            for task in run.tasks
        ],
        "results": [
            {
                "task_id": result.task_id,
                "task_name": result.task_name,
                "status": result.status,
                "output": result.output,
                "completed_at": result.completed_at,
            }
            for result in run.results
        ],
        "events": [
            {
                "event_id": event.event_id,
                "run_id": event.run_id,
                "event_type": event.event_type,
                "state": event.state,
                "task_id": event.task_id,
                "timestamp": event.timestamp,
                "details": event.details,
            }
            for event in run.events
        ],
        "traces": [
            {
                "trace_id": trace.trace_id,
                "run_id": trace.run_id,
                "task_id": trace.task_id,
                "event": trace.event,
                "state": trace.state,
                "timestamp": trace.timestamp,
                "outcome": trace.outcome,
                "next_action": trace.next_action,
            }
            for trace in run.traces
        ],
    }


def run_task2_demo() -> dict[str, Any]:
    employee = EmployeeOnboardingInput(
        employee_id="EMP-2001",
        full_name="Jordan Lee",
        email="jordan.lee@example.com",
        department="Engineering",
        manager_email="manager@example.com",
        equipment_type="Developer Laptop",
    )

    workflow = SequentialOnboardingWorkflow()
    run = workflow.execute(employee, run_id="RUN-ONBOARD-2001")
    output = serialize_run(run)

    output_dir = ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "task2_sequential_workflow.json"

    output_path.write_text(
        json.dumps(output, indent=4),
        encoding="utf-8",
    )

    return output


if __name__ == "__main__":
    result = run_task2_demo()
    print("=" * 60)
    print("TASK 2 - SEQUENTIAL ONBOARDING WORKFLOW")
    print("=" * 60)
    print(json.dumps(result, indent=4))
    print("\nEvidence saved: outputs/task2_sequential_workflow.json")
