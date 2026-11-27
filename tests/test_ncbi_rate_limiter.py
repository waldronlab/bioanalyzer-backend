"""Shared NCBI rate limiter: concurrent callers get slots spaced min_interval apart."""

import threading
import time

import pytest

from app.utils import ncbi_rate_limiter
from app.utils.ncbi_rate_limiter import wait_for_ncbi_slot


@pytest.fixture(autouse=True)
def reset_limiter(monkeypatch):
    monkeypatch.setattr(ncbi_rate_limiter, "_next_slot", 0.0)


def test_first_request_does_not_wait(monkeypatch):
    sleeps = []
    monkeypatch.setattr(ncbi_rate_limiter.time, "sleep", sleeps.append)
    wait_for_ncbi_slot(0.11)
    assert sleeps == [0.0]


def test_back_to_back_requests_are_spaced(monkeypatch):
    clock = {"now": 100.0}
    sleeps = []
    monkeypatch.setattr(ncbi_rate_limiter.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(ncbi_rate_limiter.time, "sleep", sleeps.append)
    for _ in range(3):
        wait_for_ncbi_slot(0.1)
    assert sleeps == pytest.approx([0.0, 0.1, 0.2])


def test_no_wait_once_interval_has_elapsed(monkeypatch):
    clock = {"now": 100.0}
    sleeps = []
    monkeypatch.setattr(ncbi_rate_limiter.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(ncbi_rate_limiter.time, "sleep", sleeps.append)
    wait_for_ncbi_slot(0.1)
    clock["now"] += 0.5
    wait_for_ncbi_slot(0.1)
    assert sleeps == [0.0, 0.0]


def test_negative_interval_is_treated_as_zero(monkeypatch):
    sleeps = []
    monkeypatch.setattr(ncbi_rate_limiter.time, "sleep", sleeps.append)
    wait_for_ncbi_slot(-1)
    wait_for_ncbi_slot(-1)
    assert all(s >= 0 for s in sleeps)


def test_concurrent_threads_never_exceed_rate():
    """Real threads and real clock: 8 requests at 0.05s spacing take >= 0.35s."""
    interval, n = 0.05, 8
    send_times = []
    lock = threading.Lock()

    def worker():
        wait_for_ncbi_slot(interval)
        with lock:
            send_times.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    send_times.sort()
    gaps = [b - a for a, b in zip(send_times, send_times[1:])]
    # Small tolerance for scheduler jitter; the old per-thread sleep would
    # have sent all 8 within a few milliseconds of each other.
    assert send_times[-1] - send_times[0] >= (n - 1) * interval * 0.9
    assert min(gaps) >= interval * 0.5
