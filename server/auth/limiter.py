from collections import defaultdict
from datetime import timedelta
from typing import Dict, List
from server.auth.clock import get_current_time
from server.config import settings

class RateLimiter:
    def __init__(self):
        # key -> list of timestamp floats
        self._records: Dict[str, List[float]] = defaultdict(list)

    def is_rate_limited(self, key: str, max_attempts: int, window_seconds: int) -> bool:
        now = get_current_time().timestamp()
        cutoff = now - window_seconds
        # Clean older records
        records = [t for t in self._records[key] if t > cutoff]
        self._records[key] = records
        return len(records) >= max_attempts

    def record_attempt(self, key: str) -> None:
        now = get_current_time().timestamp()
        self._records[key].append(now)

    def reset(self, key: str) -> None:
        if key in self._records:
            del self._records[key]

    def clear_all(self) -> None:
        self._records.clear()

limiter = RateLimiter()

