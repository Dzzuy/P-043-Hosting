"""Budgets and timeouts bound work, including cancelled synchronous I/O."""

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from src.agents.copilot import runtime


def test_budget_reserves_generation_and_counts_every_attempt():
    budget = runtime.RuntimeBudget(time.monotonic() + 180)
    for _ in range(8):
        budget.consume()
    assert not budget.can_continue()
    with pytest.raises(runtime.BudgetExhaustedError):
        budget.consume()
    budget = runtime.RuntimeBudget(time.monotonic() + 5)
    assert not budget.can_continue()
    with pytest.raises(runtime.BudgetExhaustedError):
        budget.timeout(30, reserve_seconds=10)


def admission(rate=10):
    return runtime.CopilotAdmission(
        SimpleNamespace(copilot_max_concurrency=4, copilot_user_concurrency=2, copilot_rate_limit=rate)
    )


def test_concurrency_and_rate_limits_release_independently():
    limit = admission()
    limit.acquire("a")
    limit.acquire("a")
    with pytest.raises(runtime.AdmissionError) as failure:
        limit.acquire("a")
    assert failure.value.status_code == 429
    limit.acquire("b")
    limit.acquire("b")
    with pytest.raises(runtime.AdmissionError) as failure:
        limit.acquire("c")
    assert failure.value.status_code == 503
    limit.release("a")
    limit.acquire("c")
    limit = admission(rate=1)
    limit.acquire("a")
    limit.release("a")
    with pytest.raises(runtime.AdmissionError) as failure:
        limit.acquire("a")
    assert 1 <= failure.value.retry_after <= 60


@pytest.mark.asyncio
async def test_timed_out_io_keeps_capacity_until_work_actually_finishes(monkeypatch):
    slot = threading.BoundedSemaphore(1)
    monkeypatch.setattr(runtime, "_slots", slot)
    entered, release = threading.Event(), threading.Event()

    def work():
        entered.set()
        release.wait(2)

    try:
        with pytest.raises(TimeoutError):
            await runtime.bounded_io(work, 0.02)
        assert entered.is_set()
        with pytest.raises(runtime.CopilotDependencyError, match="busy"):
            await runtime.bounded_io(lambda: None, 1)
    finally:
        release.set()
    for _ in range(20):
        await asyncio.sleep(0.01)
        if slot.acquire(False):
            slot.release()
            break
    else:
        raise AssertionError("completed worker did not release capacity")
