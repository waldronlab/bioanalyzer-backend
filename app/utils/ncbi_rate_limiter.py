"""One NCBI E-utilities rate limit shared by every thread in this process.

NCBI allows 10 requests/s with an API key and 3/s without, per key/IP. Each
caller used to sleep a fixed delay before its own request, which only spaces
out requests from a single thread: batch analysis and ``asyncio.to_thread``
run many fetches at once, so together they exceeded the limit and drew 429s.
This module hands out request slots spaced ``min_interval`` apart instead.

Separate uvicorn worker processes each have their own limiter, so with N
workers the combined rate can be N times higher.
"""

import threading
import time

_lock = threading.Lock()
_next_slot = 0.0


def wait_for_ncbi_slot(min_interval: float) -> None:
    """Block until this caller may send its NCBI request.

    Reserves the next free slot under a lock, then sleeps outside it, so
    waiting threads don't hold each other up beyond their reserved slot.
    """
    global _next_slot
    min_interval = max(min_interval, 0.0)
    with _lock:
        now = time.monotonic()
        slot = max(now, _next_slot)
        _next_slot = slot + min_interval
    time.sleep(slot - now)
