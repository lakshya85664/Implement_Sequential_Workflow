
import json

import pytest

from adapters import (
    AdapterResponse,
    FakeServiceAdapter,
    IntegrationBoundary,
    WorkflowMetrics,
    WorkflowObserver,
    redact,
)


@pytest.fixture
def setup_boundary():
    observer = WorkflowObserver()
    metrics = WorkflowMetrics()

    adapters = {
        "identity": FakeServiceAdapter("identity"),
        "equipment": FakeServiceAdapter("equipment"),
    }

    boundary = IntegrationBoundary(
        adapters=adapters,
        observer=observer,
        metrics=metrics,
    )

    return boundary, observer, metrics


def test_fake_adapter_success():
    adapter = FakeServiceAdapter("identity")

    response = adapter.execute(
        "create_account",
        {"employee_id": "EMP-1"},
    )

    assert response.success is True
    assert response.service == "identity"
    assert response.data["employee_id"] == "EMP-1"


def test_fake_adapter_rejects_missing_employee_id():
    adapter = FakeServiceAdapter("identity")

    response = adapter.execute(
        "create_account",
        {},
    )

    assert response.success is False
    assert "employee_id is required" in response.error


def test_fake_adapter_failure():
    adapter = FakeServiceAdapter(
        "identity",
        should_fail=True,
    )

    response = adapter.execute(
        "create_account",
        {"employee_id": "EMP-1"},
    )

    assert response.success is False
    assert "failure" in response.error.lower()


def test_integration_boundary_records_success(setup_boundary):
    boundary, observer, metrics = setup_boundary

    response = boundary.call_service(
        run_id="RUN-1",
        task_id="TASK-1",
        service_name="identity",
        action="create_account",
        payload={"employee_id": "EMP-1"},
        correlation_id="CORR-1",
    )

    assert response.success is True
    assert len(observer.events) == 1
    assert observer.events[0]["run_id"] == "RUN-1"
    assert observer.events[0]["correlation_id"] == "CORR-1"
    assert observer.events[0]["outcome"] == "success"
    assert metrics.task_successes == 1


def test_integration_boundary_records_failure(setup_boundary):
    boundary, observer, metrics = setup_boundary

    response = boundary.call_service(
        run_id="RUN-1",
        task_id="TASK-1",
        service_name="unknown_service",
        action="some_action",
        payload={"employee_id": "EMP-1"},
    )

    assert response.success is False
    assert len(observer.events) == 1
    assert observer.events[0]["outcome"] == "failure"
    assert metrics.task_failures == 1


def test_adapter_exception_is_captured(setup_boundary):
    boundary, observer, metrics = setup_boundary

    class BrokenAdapter:
        service_name = "broken"

        def execute(self, action, payload):
            raise RuntimeError("Internal test failure")

    boundary.adapters["broken"] = BrokenAdapter()

    response = boundary.call_service(
        run_id="RUN-2",
        task_id="TASK-2",
        service_name="broken",
        action="execute",
        payload={"employee_id": "EMP-2"},
    )

    assert response.success is False
    assert "RuntimeError" in response.error
    assert observer.events[0]["outcome"] == "failure"
    assert metrics.task_failures == 1


def test_sensitive_values_are_redacted():
    data = {
        "employee_id": "EMP-1",
        "password": "secret123",
        "api_key": "key-123",
        "nested": {
            "access_token": "token-123",
            "department": "Engineering",
        },
    }

    cleaned = redact(data)

    assert cleaned["employee_id"] == "EMP-1"
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["access_token"] == "[REDACTED]"
    assert cleaned["nested"]["department"] == "Engineering"


def test_observer_saves_structured_trace(tmp_path):
    observer = WorkflowObserver()

    observer.record(
        run_id="RUN-3",
        task_id="TASK-3",
        service="identity",
        outcome="success",
        duration_ms=12.5,
        correlation_id="CORR-3",
        details={"password": "hidden"},
    )

    trace_path = tmp_path / "trace.json"
    observer.save(trace_path)

    saved = json.loads(trace_path.read_text(encoding="utf-8"))

    assert len(saved) == 1
    assert saved[0]["run_id"] == "RUN-3"
    assert saved[0]["duration_ms"] == 12.5
    assert saved[0]["details"]["password"] == "[REDACTED]"


def test_metrics_track_workflow_and_task_counts():
    metrics = WorkflowMetrics()

    metrics.record_workflow_start()
    metrics.record_task(True, 10.0)
    metrics.record_task(False, 5.0)
    metrics.record_retry()
    metrics.record_workflow_completion()

    result = metrics.to_dict()

    assert result["workflow_starts"] == 1
    assert result["workflow_completions"] == 1
    assert result["task_successes"] == 1
    assert result["task_failures"] == 1
    assert result["retries"] == 1
    assert result["total_latency_ms"] == 15.0


def test_adapter_response_contract():
    response = AdapterResponse(
        success=True,
        service="identity",
        action="create_account",
        data={"employee_id": "EMP-1"},
    )

    assert response.success is True
    assert response.error is None
    assert response.data["employee_id"] == "EMP-1"


def test_injected_adapters_can_be_replaced(setup_boundary):
    boundary, _, _ = setup_boundary

    replacement = FakeServiceAdapter("identity")
    boundary.adapters["identity"] = replacement

    response = boundary.call_service(
        run_id="RUN-4",
        task_id="TASK-4",
        service_name="identity",
        action="create_account",
        payload={"employee_id": "EMP-4"},
    )

    assert response.success is True
    assert replacement.call_count == 1
