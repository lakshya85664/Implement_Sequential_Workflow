# Sequential Workflow - Operator Runbook

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

`E:\Tayana_Projects\Workflow_Orchestration\Implement_Sequential_Workflow`

Activate the environment:

```cmd
.venv\Scripts\activate
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
