
"""Task 3 - Failure, retry, and replay safety."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


# ---------------------------------------------------------
# Failure categories
# ---------------------------------------------------------

class FailureType(str, Enum):
    TRANSIENT = "transient"
    TIMEOUT = "timeout"
    PERMANENT = "permanent"
    MALFORMED = "malformed"
    DUPLICATE = "duplicate"
    UNKNOWN = "unknown"


class TransientDependencyError(Exception):
    pass


class DependencyTimeout(Exception):
    pass


class PermanentDependencyError(Exception):
    pass


class MalformedResponseError(Exception):
    pass


class DuplicateExecutionError(Exception):
    pass


# ---------------------------------------------------------
# Failure classification and operator actions
# ---------------------------------------------------------

@dataclass
class FailureDecision:
    failure_type: FailureType
    retryable: bool
    next_action: str
    reason: str


def classify_failure(exc: Exception) -> FailureDecision:
    if isinstance(exc, DependencyTimeout):
        return FailureDecision(
            FailureType.TIMEOUT,
            True,
            "retry_with_backoff",
            "Dependency exceeded its allowed response time",
        )

    if isinstance(exc, TransientDependencyError):
        return FailureDecision(
            FailureType.TRANSIENT,
            True,
            "retry_with_backoff",
            "Temporary dependency failure",
        )

    if isinstance(exc, PermanentDependencyError):
        return FailureDecision(
            FailureType.PERMANENT,
            False,
            "operator_review",
            "Permanent dependency failure; automatic retry is unsafe",
        )

    if isinstance(exc, MalformedResponseError):
        return FailureDecision(
            FailureType.MALFORMED,
            False,
            "quarantine_response",
            "Dependency returned an invalid response",
        )

    if isinstance(exc, DuplicateExecutionError):
        return FailureDecision(
            FailureType.DUPLICATE,
            False,
            "return_cached_result",
            "Duplicate execution was detected",
        )

    return FailureDecision(
        FailureType.UNKNOWN,
        False,
        "operator_review",
        "Unclassified error; automatic retry is disabled",
    )


# ---------------------------------------------------------
# Bounded retry policy
# ---------------------------------------------------------

@dataclass
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_seconds: float = 1.0
    multiplier: float = 2.0
    max_backoff_seconds: float = 8.0

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.initial_backoff_seconds < 0:
            raise ValueError("Initial backoff cannot be negative")
        if self.multiplier < 1:
            raise ValueError("Backoff multiplier must be at least 1")
        if self.max_backoff_seconds < 0:
            raise ValueError("Maximum backoff cannot be negative")

    def delay_for(self, failed_attempt: int) -> float:
        if failed_attempt < 1:
            raise ValueError("failed_attempt must be at least 1")

        delay = (
            self.initial_backoff_seconds
            * self.multiplier ** (failed_attempt - 1)
        )
        return min(delay, self.max_backoff_seconds)


# ---------------------------------------------------------
# Idempotency ledger
# ---------------------------------------------------------

@dataclass
class IdempotencyLedger:
    """Caches results by key to prevent duplicate side effects."""

    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    fingerprints: dict[str, str] = field(default_factory=dict)
    side_effect_count: int = 0

    @staticmethod
    def fingerprint(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def execute_once(
        self,
        key: str,
        payload: dict[str, Any],
        operation: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        if not key.strip():
            raise ValueError("Idempotency key cannot be empty")

        current_fingerprint = self.fingerprint(payload)

        if key in self.results:
            if self.fingerprints[key] != current_fingerprint:
                raise PermanentDependencyError(
                    "Idempotency key reused with different input"
                )
            return {
                **self.results[key],
                "idempotent_replay": True,
            }

        result = operation()

        if not isinstance(result, dict) or not result:
            raise MalformedResponseError(
                "Side-effect operation returned an invalid result"
            )

        self.results[key] = dict(result)
        self.fingerprints[key] = current_fingerprint
        self.side_effect_count += 1

        return {
            **result,
            "idempotent_replay": False,
        }


# ---------------------------------------------------------
# Safe retry executor
# ---------------------------------------------------------

@dataclass
class RetryRecord:
    attempt: int
    failure_type: str
    error: str
    retryable: bool
    backoff_seconds: float
    next_action: str


class SafeTaskExecutor:
    def __init__(
        self,
        policy: RetryPolicy | None = None,
        timeout_seconds: float = 5.0,
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self.policy = policy or RetryPolicy()
        self.timeout_seconds = timeout_seconds
        self.retry_trace: list[RetryRecord] = []

    def execute(
        self,
        operation: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        self.retry_trace.clear()

        for attempt in range(1, self.policy.max_attempts + 1):
            started = time.monotonic()

            try:
                result = operation()
                elapsed = time.monotonic() - started

                if elapsed > self.timeout_seconds:
                    raise DependencyTimeout(
                        f"Operation exceeded {self.timeout_seconds} seconds"
                    )

                if not isinstance(result, dict) or not result:
                    raise MalformedResponseError(
                        "Operation returned an empty or invalid result"
                    )

                return result

            except Exception as exc:
                decision = classify_failure(exc)
                can_retry = (
                    decision.retryable
                    and attempt < self.policy.max_attempts
                )

                delay = (
                    self.policy.delay_for(attempt)
                    if can_retry
                    else 0.0
                )

                self.retry_trace.append(
                    RetryRecord(
                        attempt=attempt,
                        failure_type=decision.failure_type.value,
                        error=str(exc),
                        retryable=can_retry,
                        backoff_seconds=delay,
                        next_action=(
                            "retry"
                            if can_retry
                            else decision.next_action
                        ),
                    )
                )

                if not can_retry:
                    raise

        raise RuntimeError("Retry executor exited unexpectedly")


# ---------------------------------------------------------
# Failure and replay demonstration
# ---------------------------------------------------------

def run_task3_demo() -> dict[str, Any]:
    ledger = IdempotencyLedger()
    executor = SafeTaskExecutor(
        RetryPolicy(max_attempts=3, initial_backoff_seconds=1),
        timeout_seconds=2,
    )

    dependency_calls = {"count": 0}

    def unstable_dependency():
        dependency_calls["count"] += 1

        if dependency_calls["count"] == 1:
            raise DependencyTimeout("First attempt timed out")

        if dependency_calls["count"] == 2:
            raise TransientDependencyError("Temporary service unavailable")

        return {"status": "success", "reference": "ACCOUNT-RECOVERED"}

    recovered_result = executor.execute(unstable_dependency)

    def account_creation_side_effect():
        return {
            "account_id": "ACC-EMP-3001",
            "status": "created",
        }

    payload = {"employee_id": "EMP-3001"}

    first_result = ledger.execute_once(
        "create-account:EMP-3001",
        payload,
        account_creation_side_effect,
    )

    replay_result = ledger.execute_once(
        "create-account:EMP-3001",
        payload,
        account_creation_side_effect,
    )

    failure_examples = {}
    for name, exc in {
        "permanent": PermanentDependencyError("Account service rejected request"),
        "malformed": MalformedResponseError("Invalid account service response"),
        "unknown": RuntimeError("Unexpected error"),
    }.items():
        decision = classify_failure(exc)
        failure_examples[name] = {
            "failure_type": decision.failure_type.value,
            "retryable": decision.retryable,
            "next_action": decision.next_action,
            "reason": decision.reason,
        }

    return {
        "recovery": {
            "result": recovered_result,
            "dependency_calls": dependency_calls["count"],
            "retry_trace": [
                record.__dict__
                for record in executor.retry_trace
            ],
        },
        "idempotency": {
            "first_result": first_result,
            "replay_result": replay_result,
            "side_effect_count": ledger.side_effect_count,
            "duplicate_prevented": ledger.side_effect_count == 1,
        },
        "failure_classification": failure_examples,
    }


def save_task3_evidence(result: dict[str, Any]) -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parent
    output_dir = root / "outputs"
    trace_dir = root / "traces"
    output_dir.mkdir(exist_ok=True)
    trace_dir.mkdir(exist_ok=True)

    (output_dir / "task3_failure_recovery.json").write_text(
        json.dumps(result, indent=4),
        encoding="utf-8",
    )

    trace = result["recovery"]["retry_trace"]
    (trace_dir / "task3_retry_trace.json").write_text(
        json.dumps(trace, indent=4),
        encoding="utf-8",
    )


if __name__ == "__main__":
    output = run_task3_demo()
    save_task3_evidence(output)

    print("=" * 60)
    print("TASK 3 - FAILURE, RETRY AND REPLAY SAFETY")
    print("=" * 60)
    print(json.dumps(output, indent=4))
    print("\nEvidence saved:")
    print("outputs/task3_failure_recovery.json")
    print("traces/task3_retry_trace.json")
