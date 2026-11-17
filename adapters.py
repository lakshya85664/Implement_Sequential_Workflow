
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
TRACE_DIR = BASE_DIR / "traces"

OUTPUT_FILE = OUTPUT_DIR / "task4_integration_observability.json"
TRACE_FILE = TRACE_DIR / "task4_observability_trace.json"


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: Any) -> Any:
    """Recursively redact sensitive values before writing logs."""
    sensitive_keys = {
        "password",
        "secret",
        "api_key",
        "token",
        "authorization",
        "access_token",
        "refresh_token",
    }

    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if str(key).lower() in sensitive_keys:
                cleaned[key] = "[REDACTED]"
            else:
                cleaned[key] = redact(item)
        return cleaned

    if isinstance(value, list):
        return [redact(item) for item in value]

    if isinstance(value, tuple):
        return [redact(item) for item in value]

    return value


@dataclass
class AdapterResponse:
    success: bool
    service: str
    action: str
    data: dict[str, Any]
    error: str | None = None


class ServiceAdapter(Protocol):
    """Contract that every external service adapter must implement."""

    service_name: str

    def execute(
        self,
        action: str,
        payload: dict[str, Any],
    ) -> AdapterResponse:
        ...


class FakeServiceAdapter:
    """
    Simulates an external service.

    Replace this implementation with a real API adapter when integrating
    identity, equipment, HR, or notification systems.
    """

    def __init__(
        self,
        service_name: str,
        should_fail: bool = False,
    ) -> None:
        self.service_name = service_name
        self.should_fail = should_fail
        self.call_count = 0

    def execute(
        self,
        action: str,
        payload: dict[str, Any],
    ) -> AdapterResponse:
        self.call_count += 1

        if not isinstance(payload, dict):
            return AdapterResponse(
                success=False,
                service=self.service_name,
                action=action,
                data={},
                error="Payload must be a dictionary",
            )

        if self.should_fail:
            return AdapterResponse(
                success=False,
                service=self.service_name,
                action=action,
                data={},
                error="Simulated external service failure",
            )

        employee_id = payload.get("employee_id")

        if not employee_id:
            return AdapterResponse(
                success=False,
                service=self.service_name,
                action=action,
                data={},
                error="employee_id is required",
            )

        result_id = (
            f"{action.upper()}-{employee_id}"
        )

        return AdapterResponse(
            success=True,
            service=self.service_name,
            action=action,
            data={
                "employee_id": employee_id,
                "result_id": result_id,
                "status": "completed",
            },
        )


class WorkflowObserver:
    """Stores structured workflow events and trace information."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(
        self,
        *,
        run_id: str,
        task_id: str,
        service: str,
        outcome: str,
        duration_ms: float,
        correlation_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        event = {
            "timestamp": timestamp(),
            "run_id": run_id,
            "task_id": task_id,
            "service": service,
            "outcome": outcome,
            "duration_ms": round(duration_ms, 3),
            "correlation_id": correlation_id,
            "details": redact(details or {}),
        }

        self.events.append(event)

    def save(self, path: Path = TRACE_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.events, indent=4),
            encoding="utf-8",
        )


class WorkflowMetrics:
    """Collects basic workflow and task metrics."""

    def __init__(self) -> None:
        self.workflow_starts = 0
        self.workflow_completions = 0
        self.workflow_failures = 0
        self.task_successes = 0
        self.task_failures = 0
        self.retries = 0
        self.total_latency_ms = 0.0

    def record_workflow_start(self) -> None:
        self.workflow_starts += 1

    def record_workflow_completion(self) -> None:
        self.workflow_completions += 1

    def record_workflow_failure(self) -> None:
        self.workflow_failures += 1

    def record_task(
        self,
        success: bool,
        duration_ms: float,
    ) -> None:
        if success:
            self.task_successes += 1
        else:
            self.task_failures += 1

        self.total_latency_ms += duration_ms

    def record_retry(self) -> None:
        self.retries += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_starts": self.workflow_starts,
            "workflow_completions": self.workflow_completions,
            "workflow_failures": self.workflow_failures,
            "task_successes": self.task_successes,
            "task_failures": self.task_failures,
            "retries": self.retries,
            "total_latency_ms": round(self.total_latency_ms, 3),
        }


class IntegrationBoundary:
    """
    Connects workflow actions to injected service adapters.

    The workflow depends on the adapter contract, not on a specific
    external provider implementation.
    """

    def __init__(
        self,
        adapters: dict[str, ServiceAdapter],
        observer: WorkflowObserver,
        metrics: WorkflowMetrics,
    ) -> None:
        self.adapters = adapters
        self.observer = observer
        self.metrics = metrics

    def call_service(
        self,
        *,
        run_id: str,
        task_id: str,
        service_name: str,
        action: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> AdapterResponse:
        correlation_id = correlation_id or str(uuid.uuid4())

        adapter = self.adapters.get(service_name)

        if adapter is None:
            response = AdapterResponse(
                success=False,
                service=service_name,
                action=action,
                data={},
                error="No adapter registered for this service",
            )
            self.metrics.record_task(False, 0.0)
            self.observer.record(
                run_id=run_id,
                task_id=task_id,
                service=service_name,
                outcome="failure",
                duration_ms=0.0,
                correlation_id=correlation_id,
                details={"error": response.error},
            )
            return response

        started = time.perf_counter()

        try:
            response = adapter.execute(action, payload)

            if not isinstance(response, AdapterResponse):
                raise TypeError(
                    "Adapter must return an AdapterResponse"
                )

        except Exception as exc:
            response = AdapterResponse(
                success=False,
                service=service_name,
                action=action,
                data={},
                error=f"Adapter exception: {type(exc).__name__}",
            )

        duration_ms = (
            time.perf_counter() - started
        ) * 1000

        self.metrics.record_task(
            response.success,
            duration_ms,
        )

        self.observer.record(
            run_id=run_id,
            task_id=task_id,
            service=service_name,
            outcome="success" if response.success else "failure",
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            details={
                "action": action,
                "request": payload,
                "response": asdict(response),
            },
        )

        return response


def run_demo() -> dict[str, Any]:
    """Run a four-step onboarding integration demonstration."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TRACE_DIR.mkdir(parents=True, exist_ok=True)

    run_id = "RUN-TASK4-001"
    employee_id = "EMP-4001"

    observer = WorkflowObserver()
    metrics = WorkflowMetrics()

    adapters: dict[str, ServiceAdapter] = {
        "identity": FakeServiceAdapter("identity"),
        "equipment": FakeServiceAdapter("equipment"),
        "hr": FakeServiceAdapter("hr"),
        "notification": FakeServiceAdapter("notification"),
    }

    boundary = IntegrationBoundary(
        adapters=adapters,
        observer=observer,
        metrics=metrics,
    )

    steps = [
        ("TASK-01", "identity", "create_account"),
        ("TASK-02", "equipment", "assign_equipment"),
        ("TASK-03", "hr", "schedule_orientation"),
        ("TASK-04", "notification", "notify_manager"),
    ]

    metrics.record_workflow_start()
    results = []
    workflow_success = True

    for task_id, service_name, action in steps:
        response = boundary.call_service(
            run_id=run_id,
            task_id=task_id,
            service_name=service_name,
            action=action,
            payload={
                "employee_id": employee_id,
                "department": "Engineering",
            },
            correlation_id=f"CORR-{task_id}",
        )

        results.append(asdict(response))

        if not response.success:
            workflow_success = False
            break

    if workflow_success:
        metrics.record_workflow_completion()
        workflow_status = "completed"
    else:
        metrics.record_workflow_failure()
        workflow_status = "failed"

    report = {
        "task": "Task 4 - Integration Boundary and Observability",
        "run_id": run_id,
        "employee_id": employee_id,
        "workflow_status": workflow_status,
        "integration_design": {
            "adapter_contract": "ServiceAdapter Protocol",
            "injection_enabled": True,
            "external_services": list(adapters.keys()),
            "implementation": "Fake adapters for demonstration",
        },
        "service_results": results,
        "metrics": metrics.to_dict(),
        "trace_event_count": len(observer.events),
        "trace_file": str(TRACE_FILE.relative_to(BASE_DIR)),
    }

    OUTPUT_FILE.write_text(
        json.dumps(report, indent=4),
        encoding="utf-8",
    )

    observer.save()

    print("=" * 60)
    print("TASK 4 - INTEGRATION AND OBSERVABILITY")
    print("=" * 60)
    print(f"Run ID: {run_id}")
    print(f"Workflow status: {workflow_status}")
    print(f"Service calls: {len(results)}")
    print(f"Trace events: {len(observer.events)}")
    print(f"Metrics: {json.dumps(metrics.to_dict(), indent=2)}")
    print(f"\nCreated: {OUTPUT_FILE}")
    print(f"Created: {TRACE_FILE}")

    return report


if __name__ == "__main__":
    run_demo()
