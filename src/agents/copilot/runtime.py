"""Per-turn budgets and bounded background I/O; no graph checkpoints."""

import asyncio
import contextvars
import math
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any


class CopilotDependencyError(RuntimeError):
    pass


class BudgetExhaustedError(RuntimeError):
    pass


@dataclass
class RuntimeBudget:
    deadline: float
    max_attempts: int = 8
    reserve_seconds: float = 10.0
    attempts: int = 0
    provider_retries: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(cls, settings):
        return cls(
            time.monotonic() + getattr(settings, "copilot_request_timeout_seconds", 180.0),
            getattr(settings, "copilot_max_llm_attempts", 8),
            getattr(settings, "copilot_final_reserve_seconds", 10.0),
        )

    def remaining(self):
        return max(0.0, self.deadline - time.monotonic())

    def can_continue(self, reserve_attempts=0):
        return self.remaining() > self.reserve_seconds and self.attempts < self.max_attempts - reserve_attempts

    def timeout(self, limit, reserve_seconds=0):
        remaining = self.remaining() - reserve_seconds
        if remaining <= 0:
            raise BudgetExhaustedError("deadline exhausted")
        return min(limit, remaining)

    def consume(self):
        if self.remaining() <= 0 or self.attempts >= self.max_attempts:
            raise BudgetExhaustedError("model budget exhausted")
        self.attempts += 1


_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="copilot-io")
_slots = threading.BoundedSemaphore(8)


async def bounded_io(function, timeout):
    from src.observability import span, worker_timeout

    # A timed-out thread keeps its slot until the actual work ends.
    if not _slots.acquire(blocking=False):
        raise CopilotDependencyError("retrieval executor busy")
    timed_out = threading.Event()

    def work():
        token = worker_timeout.set(timed_out)
        try:
            with span("io.worker"):
                return function()
        finally:
            worker_timeout.reset(token)

    def completed(result):
        _slots.release()
        if not result.cancelled():
            result.exception()

    with span("io.wait"):
        try:
            context = contextvars.copy_context()
            future = asyncio.get_running_loop().run_in_executor(_executor, context.run, work)
        except BaseException:
            _slots.release()
            raise
        future.add_done_callback(completed)
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except (TimeoutError, asyncio.CancelledError):
            timed_out.set()
            raise


class AdmissionError(RuntimeError):
    def __init__(self, status_code, retry_after):
        self.status_code = status_code
        self.retry_after = retry_after


class CopilotAdmission:
    """Single-worker limits, with bounded retention of expired user windows."""

    def __init__(self, settings):
        self.max_active = settings.copilot_max_concurrency
        self.max_user = settings.copilot_user_concurrency
        self.rate = settings.copilot_rate_limit
        self.windows = defaultdict(deque)
        self.active = defaultdict(int)
        self.lock = threading.Lock()

    def acquire(self, user_id):
        now = time.monotonic()
        with self.lock:
            for key in list(self.windows):
                window = self.windows[key]
                while window and window[0] <= now - 60:
                    window.popleft()
                if not window and not self.active.get(key):
                    self.windows.pop(key, None)
            window = self.windows[user_id]
            if len(window) >= self.rate:
                raise AdmissionError(429, max(1, math.ceil(window[0] + 60 - now)))
            if self.active.get(user_id, 0) >= self.max_user:
                raise AdmissionError(429, 1)
            if sum(self.active.values()) >= self.max_active:
                raise AdmissionError(503, 1)
            window.append(now)
            self.active[user_id] += 1

    def release(self, user_id):
        with self.lock:
            remaining = self.active.get(user_id, 0) - 1
            if remaining > 0:
                self.active[user_id] = remaining
            else:
                self.active.pop(user_id, None)
