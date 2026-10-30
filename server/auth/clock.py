from datetime import datetime, timezone
from typing import Callable, Optional

_clock_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

def set_clock_provider(fn: Callable[[], datetime]) -> None:
    global _clock_fn
    _clock_fn = fn

def reset_clock_provider() -> None:
    global _clock_fn
    _clock_fn = lambda: datetime.now(timezone.utc)

def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def get_current_time() -> datetime:
    return ensure_utc(_clock_fn())
