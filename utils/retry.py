"""Async retry with exponential backoff + simple circuit breaker."""
import asyncio
import functools
import time
from typing import Any, Callable, Tuple, Type

from utils.logger import get_logger

log = get_logger("retry")


def async_retry(
    retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
):
    def deco(fn: Callable):
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any):
            delay = base_delay
            last_exc: BaseException | None = None
            for attempt in range(1, retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as exc:  # noqa: BLE001 - deliberate broad retry
                    last_exc = exc
                    log.warning(
                        "retry %d/%d for %s after %s: %s",
                        attempt, retries, fn.__qualname__, type(exc).__name__, exc,
                    )
                    if attempt < retries:
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, max_delay)
            assert last_exc is not None
            raise last_exc

        return wrapper

    return deco


class CircuitBreaker:
    """Opens after `failure_threshold` consecutive failures; half-opens after cooldown."""

    def __init__(self, failure_threshold: int = 5, cooldown_sec: float = 60.0):
        self.failure_threshold = failure_threshold
        self.cooldown_sec = cooldown_sec
        self._failures = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if time.monotonic() - self._opened_at >= self.cooldown_sec:
            return True  # half-open trial
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold and self._opened_at is None:
            self._opened_at = time.monotonic()
            log.error("circuit breaker OPENED after %d failures", self._failures)

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None and not self.allow()
