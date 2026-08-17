from __future__ import annotations

import time
from collections.abc import Callable


def with_retry(operation: Callable[[], object], attempts: int = 3, delay: float = 1.0,
               on_retry: Callable[[int, Exception], None] | None = None):
    attempts = max(1, int(attempts))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            if on_retry:
                on_retry(attempt, exc)
            time.sleep(delay * attempt)
    assert last_error is not None
    raise last_error
