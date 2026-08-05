"""Shared concurrency control for remote and local account batch work."""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from functools import wraps
from threading import Condition, Lock, local
from typing import Callable, Iterator, ParamSpec, TypeVar


_DEFAULT_CONCURRENCY = 30
_MIN_CONCURRENCY = 1
_MAX_CONCURRENCY = 100

P = ParamSpec("P")
R = TypeVar("R")


def account_processing_concurrency() -> int:
    """Return the current configured global account-processing limit."""
    try:
        from services.config import config

        value = int(config.account_processing_concurrency)
    except (AttributeError, TypeError, ValueError):
        value = _DEFAULT_CONCURRENCY
    return max(_MIN_CONCURRENCY, min(_MAX_CONCURRENCY, value))


def account_processing_worker_count(item_count: int) -> int:
    """Size a local worker pool without exceeding the shared global limit."""
    count = max(0, int(item_count or 0))
    return min(count, account_processing_concurrency())


class AccountProcessingLimiter:
    """A process-wide, dynamically sized and thread-reentrant limiter."""

    def __init__(self) -> None:
        self._condition = Condition(Lock())
        self._active = 0
        self._local = local()

    @contextmanager
    def slot(self) -> Iterator[None]:
        depth = int(getattr(self._local, "depth", 0) or 0)
        if depth:
            self._local.depth = depth + 1
            try:
                yield
            finally:
                self._local.depth = depth
            return

        with self._condition:
            while self._active >= account_processing_concurrency():
                self._condition.wait(timeout=0.5)
            self._active += 1
            self._local.depth = 1
        try:
            yield
        finally:
            self._local.depth = 0
            with self._condition:
                self._active = max(0, self._active - 1)
                self._condition.notify_all()

    @contextmanager
    def batch_slot(self) -> Iterator[None]:
        """Reserve one shared slot for the lifetime of an account batch.

        Batch work and individual upstream requests share the same limiter and
        thread-local re-entry depth.  A batch may therefore call code that
        acquires a regular slot on its coordinator thread without consuming a
        second slot or deadlocking when the configured limit is one.
        """
        with self.slot():
            yield


account_processing_limiter = AccountProcessingLimiter()


def account_processing_slot() -> AbstractContextManager[None]:
    """Acquire one shared slot for an upstream account-maintenance request."""
    return account_processing_limiter.slot()


def account_processing_batch_slot() -> AbstractContextManager[None]:
    """Acquire one shared slot for a complete local account batch mutation.

    The slot is intentionally the same limiter used by remote maintenance. A
    local mutation stays atomic inside the account service, but still participates
    in the one process-wide capacity budget.
    """
    return account_processing_limiter.batch_slot()


def account_processing_batch(
    function: Callable[P, R],
) -> Callable[P, R]:
    """Decorate a synchronous account batch entry point with one shared slot."""

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        with account_processing_batch_slot():
            return function(*args, **kwargs)

    return wrapped
