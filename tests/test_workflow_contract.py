
import pytest

from sequential_workflow import (
    EmployeeOnboardingInput,
    WorkflowRun,
    WorkflowState,
    TaskStatus,
    LEGAL_TRANSITIONS,
    create_onboarding_tasks,
    transition,
    run_topic_fixture,
)


def create_test_run():
    return WorkflowRun(
        run_id="RUN-TEST-001",
        business_key="EMP-TEST-001",
    )


def test_employee_input_accepts_valid_data():
    employee = EmployeeOnboardingInput(
        employee_id="EMP-1001",
        full_name="Alex Morgan",
        email="ALEX@EXAMPLE.COM",
        department="Engineering",
        manager_email="MANAGER@EXAMPLE.COM",
        equipment_type="Developer Laptop",
    )

    assert employee.employee_id == "EMP-1001"
    assert employee.email == "alex@example.com"


def test_employee_input_rejects_invalid_email():
    with pytest.raises(ValueError):
        EmployeeOnboardingInput(
            employee_id="EMP-1001",
            full_name="Alex Morgan",
            email="invalid-email",
            department="Engineering",
            manager_email="manager@example.com",
            equipment_type="Developer Laptop",
        )


def test_workflow_starts_in_created_state():
    run = create_test_run()

    assert run.state == WorkflowState.CREATED


def test_legal_transition_created_to_running():
    run = create_test_run()

    transition(run, "start")

    assert run.state == WorkflowState.RUNNING
    assert len(run.events) == 1
    assert len(run.traces) == 1


def test_illegal_transition_is_rejected():
    run = create_test_run()

    with pytest.raises(ValueError, match="Illegal workflow transition"):
        transition(run, "complete")


def test_onboarding_tasks_have_correct_sequence():
    tasks = create_onboarding_tasks()

    assert len(tasks) == 4
    assert [task.sequence for task in tasks] == [1, 2, 3, 4]


def test_task_dependencies_are_sequential():
    tasks = create_onboarding_tasks()

    assert tasks[0].dependency is None
    assert tasks[1].dependency == tasks[0].task_id
    assert tasks[2].dependency == tasks[1].task_id
    assert tasks[3].dependency == tasks[2].task_id


def test_all_tasks_start_pending():
    tasks = create_onboarding_tasks()

    assert all(task.status == TaskStatus.PENDING for task in tasks)


def test_state_transition_table_contains_expected_transitions():
    assert LEGAL_TRANSITIONS[
        (WorkflowState.CREATED, "start")
    ] == WorkflowState.RUNNING

    assert LEGAL_TRANSITIONS[
        (WorkflowState.RUNNING, "complete")
    ] == WorkflowState.COMPLETED


def test_task1_fixture_generates_evidence():
    result = run_topic_fixture()

    assert result["run_id"] == "RUN-ONBOARD-1001"
    assert result["state"] == "running"
    assert len(result["task_sequence"]) == 4
    assert len(result["events"]) >= 1
    assert len(result["traces"]) >= 1
