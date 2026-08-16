"""Token-bucket async rate limiter respecting Bybit request budgets."""
import asyncio
import time


class RateLimiter:
    def __init__(self, rate: float = 10.0, burst: int = 20):
        """rate: tokens per second; burst: bucket capacity."""
        self.rate = rate
        self.capacity = burst
        self._tokens = float(burst)
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                wait = (tokens - self._tokens) / self.rate
                # release lock while sleeping
                self._lock.release()
                try:
                    await asyncio.sleep(wait)
                finally:
                    await self._lock.acquire()
