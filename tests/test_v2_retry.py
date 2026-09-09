"""D3 retry tests: deterministic, no sleeps, no network."""

import pytest

from v2.errors import ErrorCategory, IngestionError
from v2.retry import (RetryPolicy, compute_backoff, is_retryable_category,
                      run_with_retry)


def noop_sleep(_seconds):
    pass


def policy(**overrides):
    defaults = {"max_attempts": 3, "sleep_fn": noop_sleep}
    defaults.update(overrides)
    return RetryPolicy(**defaults)


def test_backoff_is_deterministic():
    assert compute_backoff(1, 2.0, 2.0, 60.0) == 2.0
    assert compute_backoff(2, 2.0, 2.0, 60.0) == 4.0
    assert compute_backoff(99, 2.0, 2.0, 5.0) == 5.0  # capped


def test_transient_then_success():
    calls = []

    def flaky(attempt):
        calls.append(attempt)
        if attempt < 3:
            raise IngestionError.transient("hiccup")
        return "ok"

    outcome = run_with_retry(flaky, policy())
    assert outcome.value == "ok"
    assert outcome.attempts == 3
    assert calls == [1, 2, 3]


def test_budget_exhaustion_reraises_last_error():
    def always_fail(attempt):
        raise IngestionError.transient(f"down-{attempt}")

    with pytest.raises(IngestionError) as exc_info:
        run_with_retry(always_fail, policy(max_attempts=3))
    assert "down-3" in str(exc_info.value)


def test_non_retryable_fails_fast():
    calls = []

    def invalid(attempt):
        calls.append(attempt)
        raise IngestionError.validation("bad frame")

    with pytest.raises(IngestionError):
        run_with_retry(invalid, policy(max_attempts=5))
    assert calls == [1]  # exactly one attempt, no retry


def test_unexpected_exceptions_propagate_untouched():
    with pytest.raises(ZeroDivisionError):
        run_with_retry(lambda attempt: 1 / 0, policy())


def test_max_attempts_one_means_no_retry():
    calls = []

    def fail(attempt):
        calls.append(attempt)
        raise IngestionError.transient("x")

    with pytest.raises(IngestionError):
        run_with_retry(fail, policy(max_attempts=1))
    assert calls == [1]


def test_retryable_mapping():
    assert is_retryable_category(ErrorCategory.TRANSIENT)
    assert is_retryable_category(ErrorCategory.STORAGE)
    assert not is_retryable_category(ErrorCategory.VALIDATION)
    assert not is_retryable_category(ErrorCategory.MISSING_SESSION)
    assert not is_retryable_category(ErrorCategory.CONFIG)


def test_backoff_sleeps_are_injected_not_real():
    slept = []

    def boom(attempt):
        raise IngestionError.transient("x")

    with pytest.raises(IngestionError):
        run_with_retry(boom, policy(max_attempts=3,
                                    sleep_fn=slept.append,
                                    backoff_base_s=2.0, backoff_factor=2.0,
                                    backoff_max_s=60.0))
    assert slept == [2.0, 4.0]
