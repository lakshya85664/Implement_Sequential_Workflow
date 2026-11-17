
"""Topic 3 - Sequential Workflow: workflow contract and state model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------
# 1. Workflow and task states
# ---------------------------------------------------------

class WorkflowState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------
# 2. Typed employee onboarding input
# ---------------------------------------------------------

class EmployeeOnboardingInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    employee_id: str = Field(min_length=3, max_length=40)
    full_name: str = Field(min_length=2, max_length=100)
    email: str
    department: str = Field(min_length=2, max_length=60)
    manager_email: str
    equipment_type: str = Field(min_length=2, max_length=60)

    @field_validator("email", "manager_email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError("A valid email address is required")
        return value.lower()


# ---------------------------------------------------------
# 3. Task, result, event, and trace models
# ---------------------------------------------------------

@dataclass
class WorkflowTask:
    task_id: str
    name: str
    sequence: int
    dependency: str | None = None
    owner: str = "onboarding_system"
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    result: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    task_id: str
    task_name: str
    status: str
    output: dict[str, Any]
    completed_at: str


@dataclass
class WorkflowEvent:
    event_id: str
    run_id: str
    event_type: str
    state: str
    task_id: str | None
    timestamp: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceRecord:
    trace_id: str
    run_id: str
    task_id: str | None
    event: str
    state: str
    timestamp: str
    outcome: str
    next_action: str


# ---------------------------------------------------------
# 4. Workflow run model
# ---------------------------------------------------------

@dataclass
class WorkflowRun:
    run_id: str
    business_key: str
    state: WorkflowState = WorkflowState.CREATED
    attempts: int = 0
    context: dict[str, Any] = field(default_factory=dict)
    tasks: list[WorkflowTask] = field(default_factory=list)
    events: list[WorkflowEvent] = field(default_factory=list)
    results: list[TaskResult] = field(default_factory=list)
    traces: list[TraceRecord] = field(default_factory=list)

    def record_event(
        self,
        event_type: str,
        task_id: str | None = None,
        **details: Any,
    ) -> WorkflowEvent:
        event = WorkflowEvent(
            event_id=str(uuid4()),
            run_id=self.run_id,
            event_type=event_type,
            state=self.state.value,
            task_id=task_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=details,
        )
        self.events.append(event)
        return event

    def record_trace(
        self,
        event: str,
        task_id: str | None,
        outcome: str,
        next_action: str,
    ) -> TraceRecord:
        trace = TraceRecord(
            trace_id=str(uuid4()),
            run_id=self.run_id,
            task_id=task_id,
            event=event,
            state=self.state.value,
            timestamp=datetime.now(timezone.utc).isoformat(),
            outcome=outcome,
            next_action=next_action,
        )
        self.traces.append(trace)
        return trace


# ---------------------------------------------------------
# 5. Legal workflow state transitions
# ---------------------------------------------------------

LEGAL_TRANSITIONS = {
    (WorkflowState.CREATED, "start"): WorkflowState.RUNNING,
    (WorkflowState.RUNNING, "pause"): WorkflowState.WAITING,
    (WorkflowState.WAITING, "resume"): WorkflowState.RUNNING,
    (WorkflowState.RUNNING, "complete"): WorkflowState.COMPLETED,
    (WorkflowState.RUNNING, "review"): WorkflowState.NEEDS_REVIEW,
    (WorkflowState.RUNNING, "fail"): WorkflowState.FAILED,
    (WorkflowState.WAITING, "fail"): WorkflowState.FAILED,
    (WorkflowState.NEEDS_REVIEW, "resume"): WorkflowState.RUNNING,
}


def transition(
    run: WorkflowRun,
    action: str,
) -> WorkflowRun:
    """Apply a legal state transition or reject the requested action."""

    next_state = LEGAL_TRANSITIONS.get((run.state, action))

    if next_state is None:
        raise ValueError(
            f"Illegal workflow transition: {run.state.value} -> {action}"
        )

    previous_state = run.state
    run.state = next_state

    run.record_event(
        "workflow.state_changed",
        previous_state=previous_state.value,
        action=action,
        new_state=next_state.value,
    )

    run.record_trace(
        event="workflow.state_changed",
        task_id=None,
        outcome=f"{previous_state.value} -> {next_state.value}",
        next_action=action,
    )

    return run


# ---------------------------------------------------------
# 6. Ordered onboarding task definitions
# ---------------------------------------------------------

def create_onboarding_tasks() -> list[WorkflowTask]:
    return [
        WorkflowTask(
            task_id="TASK-01",
            name="create_employee_account",
            sequence=1,
            dependency=None,
            owner="identity_team",
        ),
        WorkflowTask(
            task_id="TASK-02",
            name="assign_equipment",
            sequence=2,
            dependency="TASK-01",
            owner="it_team",
        ),
        WorkflowTask(
            task_id="TASK-03",
            name="schedule_orientation",
            sequence=3,
            dependency="TASK-02",
            owner="hr_team",
        ),
        WorkflowTask(
            task_id="TASK-04",
            name="notify_manager",
            sequence=4,
            dependency="TASK-03",
            owner="notification_service",
        ),
    ]


# ---------------------------------------------------------
# 7. Deterministic Task 1 fixture
# ---------------------------------------------------------

def run_topic_fixture() -> dict[str, Any]:
    employee = EmployeeOnboardingInput(
        employee_id="EMP-1001",
        full_name="Alex Morgan",
        email="alex.morgan@example.com",
        department="Engineering",
        manager_email="manager@example.com",
        equipment_type="Developer Laptop",
    )

    run = WorkflowRun(
        run_id="RUN-ONBOARD-1001",
        business_key=employee.employee_id,
        context=employee.model_dump(),
        tasks=create_onboarding_tasks(),
    )

    transition(run, "start")

    run.record_event(
        "onboarding.workflow_started",
        employee_id=employee.employee_id,
        task_count=len(run.tasks),
    )

    output = {
        "employee": employee.model_dump(),
        "run_id": run.run_id,
        "business_key": run.business_key,
        "state": run.state.value,
        "task_sequence": [
            {
                "task_id": task.task_id,
                "name": task.name,
                "sequence": task.sequence,
                "dependency": task.dependency,
                "owner": task.owner,
                "status": task.status.value,
            }
            for task in run.tasks
        ],
        "events": [
            {
                "event_id": event.event_id,
                "run_id": event.run_id,
                "event_type": event.event_type,
                "state": event.state,
                "timestamp": event.timestamp,
                "details": event.details,
            }
            for event in run.events
        ],
        "traces": [
            {
                "trace_id": trace.trace_id,
                "run_id": trace.run_id,
                "event": trace.event,
                "state": trace.state,
                "outcome": trace.outcome,
                "next_action": trace.next_action,
                "timestamp": trace.timestamp,
            }
            for trace in run.traces
        ],
    }

    output_dir = ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / "task1_workflow_contract.json"
    output_path.write_text(
        json.dumps(output, indent=4),
        encoding="utf-8",
    )

    return output


if __name__ == "__main__":
    result = run_topic_fixture()
    print("=" * 60)
    print("TASK 1 - SEQUENTIAL WORKFLOW CONTRACT")
    print("=" * 60)
    print(json.dumps(result, indent=4))
    print("\nEvidence saved: outputs/task1_workflow_contract.json")
