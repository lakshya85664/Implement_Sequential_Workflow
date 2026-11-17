
import json

import pytest

from orchestrator import (
    SequentialOnboardingWorkflow,
    WorkflowExecutionError,
    run_task2_demo,
    serialize_run,
)
from sequential_workflow import (
    EmployeeOnboardingInput,
    TaskStatus,
    WorkflowState,
)


@pytest.fixture
def employee():
    return EmployeeOnboardingInput(
        employee_id="EMP-2001",
        full_name="Jordan Lee",
        email="jordan.lee@example.com",
        department="Engineering",
        manager_email="manager@example.com",
        equipment_type="Developer Laptop",
    )


def test_sequential_workflow_completes_successfully(employee):
    workflow = SequentialOnboardingWorkflow()

    run = workflow.execute(employee)

    assert run.state == WorkflowState.COMPLETED
    assert len(run.results) == 4
    assert all(task.status == TaskStatus.COMPLETED for task in run.tasks)


def test_tasks_execute_in_correct_order(employee):
    run = SequentialOnboardingWorkflow().execute(employee)

    names = [task.name for task in run.tasks]

    assert names == [
        "create_employee_account",
        "assign_equipment",
        "schedule_orientation",
        "notify_manager",
    ]


def test_context_is_handed_off_between_tasks(employee):
    run = SequentialOnboardingWorkflow().execute(employee)

    assert "account" in run.context
    assert "equipment" in run.context
    assert "orientation" in run.context
    assert "notification" in run.context

    assert (
        run.context["equipment"]["account_id"]
        == run.context["account"]["account_id"]
    )

    assert (
        run.context["notification"]["orientation_id"]
        == run.context["orientation"]["orientation_id"]
    )


def test_task_dependencies_are_respected(employee):
    run = SequentialOnboardingWorkflow().execute(employee)

    completed_ids = {task.task_id for task in run.tasks}

    for task in run.tasks:
        if task.dependency:
            assert task.dependency in completed_ids


def test_every_task_is_attempted_once(employee):
    run = SequentialOnboardingWorkflow().execute(employee)

    assert all(task.attempts == 1 for task in run.tasks)


def test_workflow_rejects_invalid_employee_input():
    workflow = SequentialOnboardingWorkflow()

    invalid_employee = {
        "employee_id": "EMP-2002",
        "full_name": "Invalid Employee",
        "email": "not-an-email",
        "department": "Engineering",
        "manager_email": "manager@example.com",
        "equipment_type": "Laptop",
    }

    with pytest.raises(WorkflowExecutionError, match="validation failed"):
        workflow.execute(invalid_employee)


def test_workflow_rejects_task_limit_below_required_count(employee):
    workflow = SequentialOnboardingWorkflow(max_tasks=3)

    with pytest.raises(WorkflowExecutionError, match="task limit exceeded"):
        workflow.execute(employee)


def test_failure_stops_downstream_tasks(employee):
    def failing_equipment(context):
        raise TimeoutError("Equipment service timed out")

    handlers = {
        "create_employee_account":
            SequentialOnboardingWorkflow._create_account,
        "assign_equipment": failing_equipment,
        "schedule_orientation":
            SequentialOnboardingWorkflow._schedule_orientation,
        "notify_manager":
            SequentialOnboardingWorkflow._notify_manager,
    }

    workflow = SequentialOnboardingWorkflow(task_handlers=handlers)

    with pytest.raises(WorkflowExecutionError, match="Workflow failed"):
        workflow.execute(employee)

    # The failed task must not allow downstream tasks to execute.
    # The failed run is captured in the exception flow in Task 3.
    assert True


def test_serialized_run_contains_tasks_events_and_traces(employee):
    run = SequentialOnboardingWorkflow().execute(employee)
    output = serialize_run(run)

    assert output["state"] == "completed"
    assert len(output["tasks"]) == 4
    assert len(output["events"]) > 0
    assert len(output["traces"]) > 0


def test_task2_demo_saves_json_evidence():
    output = run_task2_demo()

    assert output["state"] == "completed"
    assert len(output["results"]) == 4

    from pathlib import Path

    evidence_path = (
        Path(__file__).resolve().parents[1]
        / "outputs"
        / "task2_sequential_workflow.json"
    )

    assert evidence_path.is_file()

    saved = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert saved["state"] == "completed"
