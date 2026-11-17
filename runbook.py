
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = BASE_DIR / "outputs"
TRACE_DIR = BASE_DIR / "traces"
REPORT_DIR = BASE_DIR / "reports"

EVIDENCE_FILE = REPORT_DIR / "evidence_report.json"
SUMMARY_FILE = OUTPUT_DIR / "task5_operator_report.json"
RUNBOOK_FILE = REPORT_DIR / "OPERATOR_RUNBOOK.md"


EVIDENCE_FILES = {
    "task1_workflow_contract": OUTPUT_DIR / "task1_workflow_contract.json",
    "task2_sequential_workflow": OUTPUT_DIR / "task2_sequential_workflow.json",
    "task3_failure_recovery": OUTPUT_DIR / "task3_failure_recovery.json",
    "task3_retry_trace": TRACE_DIR / "task3_retry_trace.json",
    "task4_integration_observability": (
        OUTPUT_DIR / "task4_integration_observability.json"
    ),
    "task4_observability_trace": (
        TRACE_DIR / "task4_observability_trace.json"
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()



def inspect_json_file(path: Path) -> dict[str, Any]:
    """Check whether an evidence file exists and contains valid JSON."""

    try:
        display_path = str(path.relative_to(BASE_DIR))
    except ValueError:
        # Test files may be located outside the project directory.
        display_path = str(path)

    result = {
        "path": display_path,
        "exists": path.exists(),
        "valid_json": False,
        "size_bytes": 0,
        "error": None,
    }

    if not path.exists():
        result["error"] = "Evidence file is missing"
        return result

    result["size_bytes"] = path.stat().st_size

    try:
        with path.open("r", encoding="utf-8") as file:
            json.load(file)

        result["valid_json"] = True

    except (json.JSONDecodeError, OSError) as exc:
        result["error"] = str(exc)

    return result


def generate_evidence_inventory() -> dict[str, Any]:
    """Inspect all expected evidence files."""

    inventory = {
        name: inspect_json_file(path)
        for name, path in EVIDENCE_FILES.items()
    }

    total = len(inventory)
    existing = sum(item["exists"] for item in inventory.values())
    valid = sum(item["valid_json"] for item in inventory.values())

    return {
        "total_expected_files": total,
        "existing_files": existing,
        "valid_json_files": valid,
        "missing_files": [
            name
            for name, item in inventory.items()
            if not item["exists"]
        ],
        "invalid_files": [
            name
            for name, item in inventory.items()
            if item["exists"] and not item["valid_json"]
        ],
        "complete": existing == total and valid == total,
        "files": inventory,
    }


def load_task4_metrics() -> dict[str, Any]:
    path = EVIDENCE_FILES["task4_integration_observability"]

    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return data.get("metrics", {})

    except (json.JSONDecodeError, OSError):
        return {}


def build_runbook() -> str:
    return """# Sequential Workflow - Operator Runbook

## 1. Purpose

This runbook explains how to operate, inspect, troubleshoot, and recover
the employee onboarding sequential workflow.

The workflow contains four ordered activities:

1. Create the employee account.
2. Assign equipment.
3. Schedule orientation.
4. Notify the manager.

Each activity depends on the successful completion of the preceding step.

## 2. Environment and startup

Requirements:

- Python 3.13 or compatible Python version.
- Project virtual environment.
- pytest for automated tests.

Open Windows CMD and navigate to:

`E:\\Tayana_Projects\\Workflow_Orchestration\\Implement_Sequential_Workflow`

Activate the environment:

```cmd
.venv\\Scripts\\activate
```

Run the workflow demonstrations:

```cmd
python sequential_workflow.py
python orchestrator.py
python reliability.py
python adapters.py
```

Run all automated tests:

```cmd
python -m pytest -v
```

## 3. Workflow execution order

| Step | Activity | Responsible service |
|---|---|---|
| 1 | Create employee account | Identity |
| 2 | Assign equipment | IT |
| 3 | Schedule orientation | HR |
| 4 | Notify manager | Notification |

Do not manually mark a dependent task as completed when its prerequisite
has failed.

## 4. Monitoring and evidence

Inspect the following directories:

- `outputs/` - workflow results and task reports.
- `traces/` - execution and retry traces.
- `reports/` - operator documentation and evidence summaries.

Task 4 records structured events containing run ID, task ID, service,
outcome, duration, and correlation ID.

Sensitive fields such as passwords, secrets, API keys, and tokens should
not be written to operational logs.

## 5. Failure handling

### Transient service failure

1. Inspect the failure classification.
2. Check whether the failure is marked retryable.
3. Apply the configured bounded retry policy.
4. Confirm the final result before proceeding.

### Timeout

1. Inspect the retry trace.
2. Check the dependency's availability.
3. Retry only when the policy permits it.
4. Escalate if the retry limit is exhausted.

### Permanent failure

1. Stop automatic retries.
2. Record the failed task and error classification.
3. Send the case for operator review.
4. Resolve the dependency issue before replaying the workflow.

### Malformed response

1. Do not treat the response as a successful result.
2. Quarantine or inspect the response.
3. Verify the integration contract.
4. Replay only after the response issue is resolved.

## 6. Idempotency and replay safety

Idempotency prevents duplicate side effects when a workflow operation
is retried or replayed.

Before replaying:

- Verify the employee and task identifiers.
- Check whether the operation already succeeded.
- Reuse the original idempotency key for the same logical operation.
- Never reuse an idempotency key for different input data.

The Task 3 demonstration verifies that replay does not create a duplicate
account side effect.

## 7. Integration troubleshooting

Task 4 uses injectable service adapters.

If an integration fails:

1. Identify the service from the trace.
2. Inspect the task ID and correlation ID.
3. Check the adapter response and error classification.
4. Verify the payload contract.
5. Replace or repair the adapter implementation as required.

The supplied adapters are simulated implementations. Live provider
credentials and external API connectivity must be configured separately
before production use.

## 8. Recovery checklist

- [ ] Identify the failed workflow run.
- [ ] Identify the failed task.
- [ ] Inspect the corresponding trace.
- [ ] Classify the error.
- [ ] Check retry eligibility.
- [ ] Verify idempotency before replay.
- [ ] Confirm downstream task prerequisites.
- [ ] Record the final recovery outcome.

## 9. Operational limitations

The demonstration uses simulated external services and local JSON evidence.
It does not provide production authentication, distributed locking,
persistent external queues, or live provider monitoring.

The retry demonstration records backoff decisions; it does not establish
a production-grade scheduler or forcibly interrupt blocked synchronous
requests.

Production deployment requires provider-specific adapters, secure secret
management, durable state storage, access control, and operational alerts.
"""


def generate_reports() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    inventory = generate_evidence_inventory()
    metrics = load_task4_metrics()

    report = {
        "task": "Task 5 - Operator Runbook and Evidence Report",
        "generated_at": utc_now(),
        "project": "Implement Sequential Workflow",
        "assessment_status": (
            "evidence_complete"
            if inventory["complete"]
            else "evidence_incomplete"
        ),
        "evidence_inventory": inventory,
        "task4_metrics": metrics,
        "operational_guidance": {
            "runbook": str(RUNBOOK_FILE.relative_to(BASE_DIR)),
            "recovery_procedures_documented": True,
            "replay_safety_documented": True,
            "integration_limitations_documented": True,
        },
    }

    RUNBOOK_FILE.write_text(
        build_runbook(),
        encoding="utf-8",
    )

    EVIDENCE_FILE.write_text(
        json.dumps(report, indent=4),
        encoding="utf-8",
    )

    SUMMARY_FILE.write_text(
        json.dumps(report, indent=4),
        encoding="utf-8",
    )

    print("=" * 60)
    print("TASK 5 - OPERATOR RUNBOOK AND EVIDENCE REPORT")
    print("=" * 60)
    print(f"Evidence files expected: {inventory['total_expected_files']}")
    print(f"Evidence files found: {inventory['existing_files']}")
    print(f"Valid JSON files: {inventory['valid_json_files']}")
    print(f"Evidence complete: {inventory['complete']}")

    if inventory["missing_files"]:
        print("Missing files:", inventory["missing_files"])

    if inventory["invalid_files"]:
        print("Invalid files:", inventory["invalid_files"])

    print(f"\nCreated: {RUNBOOK_FILE}")
    print(f"Created: {EVIDENCE_FILE}")
    print(f"Created: {SUMMARY_FILE}")

    return report


if __name__ == "__main__":
    generate_reports()
