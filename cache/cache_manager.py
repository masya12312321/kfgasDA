"""In-memory TTL cache (Redis-pluggable interface)."""
from __future__ import annotations

import time
from typing import Any, Optional


class TTLCache:
    def __init__(self):
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if item is None:
            return None
        expires, value = item
        if expires < time.monotonic():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl: float = 30.0) -> None:
        self._store[key] = (time.monotonic() + ttl, value)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear_expired(self) -> int:
        now = time.monotonic()
        dead = [k for k, (exp, _) in self._store.items() if exp < now]
        for k in dead:
            self._store.pop(k, None)
        return len(dead)

    def __len__(self) -> int:
        return len(self._store)


cache = TTLCache()
