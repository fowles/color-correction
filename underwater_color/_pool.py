# SPDX-License-Identifier: MIT
"""Thread-pool helpers.

Copied from photogen rather than shared: depending on photogen would invert
the direction of the extraction, and these are twenty-five stable lines.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager


def max_workers() -> int:
    """Max thread pool workers: all but 2 CPUs, but at least 1."""
    return max((os.cpu_count() or 4) - 2, 1)


@contextmanager
def interruptible_pool(workers: int):
    """A ``ThreadPoolExecutor`` that abandons queued work when interrupted.

    ``ThreadPoolExecutor.__exit__`` calls ``shutdown(wait=True)`` and does NOT
    cancel pending futures, so a Ctrl-C with a large queue submitted up front
    blocks until every last item has run — on a big run that is tens of
    minutes during which Ctrl-C looks like it did nothing. Cancelling the queue
    bounds the wait to the tasks already in flight (at most ``workers``).

    Threads cannot be killed, so in-flight tasks still finish; that is the
    floor, not a bug.
    """
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        yield pool
    except BaseException:  # KeyboardInterrupt is not an Exception
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)
