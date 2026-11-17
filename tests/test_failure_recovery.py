
import pytest

from reliability import (
    DependencyTimeout,
    DuplicateExecutionError,
    FailureType,
    IdempotencyLedger,
    MalformedResponseError,
    PermanentDependencyError,
    RetryPolicy,
    SafeTaskExecutor,
    TransientDependencyError,
    classify_failure,
    run_task3_demo,
    save_task3_evidence,
)


def test_transient_failure_is_classified_as_retryable():
    decision = classify_failure(
        TransientDependencyError("Temporary failure")
    )

    assert decision.failure_type == FailureType.TRANSIENT
    assert decision.retryable is True
    assert decision.next_action == "retry_with_backoff"


def test_timeout_is_classified_as_retryable():
    decision = classify_failure(DependencyTimeout("Timed out"))

    assert decision.failure_type == FailureType.TIMEOUT
    assert decision.retryable is True


def test_permanent_failure_is_not_retryable():
    decision = classify_failure(
        PermanentDependencyError("Rejected")
    )

    assert decision.failure_type == FailureType.PERMANENT
    assert decision.retryable is False
    assert decision.next_action == "operator_review"


def test_malformed_response_is_quarantined():
    decision = classify_failure(
        MalformedResponseError("Invalid response")
    )

    assert decision.failure_type == FailureType.MALFORMED
    assert decision.next_action == "quarantine_response"


def test_retry_policy_uses_bounded_exponential_backoff():
    policy = RetryPolicy(
        max_attempts=4,
        initial_backoff_seconds=1,
        multiplier=2,
        max_backoff_seconds=3,
    )

    assert policy.delay_for(1) == 1
    assert policy.delay_for(2) == 2
    assert policy.delay_for(3) == 3
    assert policy.delay_for(4) == 3


def test_retry_executor_recovers_after_transient_errors():
    calls = {"count": 0}

    def operation():
        calls["count"] += 1

        if calls["count"] < 3:
            raise TransientDependencyError("Try again")

        return {"status": "success"}

    executor = SafeTaskExecutor(
        RetryPolicy(max_attempts=3),
    )

    result = executor.execute(operation)

    assert result["status"] == "success"
    assert calls["count"] == 3
    assert len(executor.retry_trace) == 2


def test_retry_executor_does_not_retry_permanent_failure():
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        raise PermanentDependencyError("Rejected")

    executor = SafeTaskExecutor(RetryPolicy(max_attempts=3))

    with pytest.raises(PermanentDependencyError):
        executor.execute(operation)

    assert calls["count"] == 1
    assert len(executor.retry_trace) == 1
    assert executor.retry_trace[0].next_action == "operator_review"


def test_retry_exhaustion_records_final_action():
    def operation():
        raise DependencyTimeout("Always times out")

    executor = SafeTaskExecutor(RetryPolicy(max_attempts=2))

    with pytest.raises(DependencyTimeout):
        executor.execute(operation)

    assert len(executor.retry_trace) == 2
    assert executor.retry_trace[-1].retryable is False


def test_idempotency_prevents_duplicate_side_effect():
    ledger = IdempotencyLedger()
    calls = {"count": 0}

    def create_account():
        calls["count"] += 1
        return {"account_id": "ACC-1"}

    payload = {"employee_id": "EMP-1"}

    first = ledger.execute_once("account:EMP-1", payload, create_account)
    second = ledger.execute_once("account:EMP-1", payload, create_account)

    assert first["account_id"] == second["account_id"]
    assert second["idempotent_replay"] is True
    assert calls["count"] == 1
    assert ledger.side_effect_count == 1


def test_idempotency_key_cannot_be_reused_for_different_input():
    ledger = IdempotencyLedger()

    ledger.execute_once(
        "account:EMP-1",
        {"employee_id": "EMP-1"},
        lambda: {"account_id": "ACC-1"},
    )

    with pytest.raises(PermanentDependencyError):
        ledger.execute_once(
            "account:EMP-1",
            {"employee_id": "EMP-2"},
            lambda: {"account_id": "ACC-2"},
        )


def test_empty_operation_result_is_rejected():
    executor = SafeTaskExecutor()

    with pytest.raises(MalformedResponseError):
        executor.execute(lambda: {})


def test_retry_policy_rejects_invalid_limits():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)


def test_task3_demo_proves_duplicate_prevention():
    result = run_task3_demo()

    assert result["recovery"]["result"]["status"] == "success"
    assert result["recovery"]["dependency_calls"] == 3
    assert result["idempotency"]["side_effect_count"] == 1
    assert result["idempotency"]["duplicate_prevented"] is True


def test_task3_evidence_files_are_generated():
    result = run_task3_demo()
    save_task3_evidence(result)

    from pathlib import Path

    root = Path(__file__).resolve().parents[1]

    assert (root / "outputs" / "task3_failure_recovery.json").is_file()
    assert (root / "traces" / "task3_retry_trace.json").is_file()
