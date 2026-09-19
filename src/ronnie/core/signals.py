"""Minimal signal dispatcher (observer pattern) — a compact ``django.dispatch``.

Usage::

    from ronnie.core.signals import request_finished

    def close_conn(sender, **kwargs): ...
    request_finished.connect(close_conn, dispatch_uid="close-conn")

    request_finished.send(sender=self)
"""

from __future__ import annotations

import threading
import weakref
from collections.abc import Callable
from typing import Any

__all__ = ["Signal", "request_finished", "request_started", "setting_changed"]


class Signal:
    """A list of receivers invoked with ``send(sender, **kwargs)``."""

    def __init__(self) -> None:
        self._receivers: list[tuple[Any, Callable[..., Any]]] = []
        self._lock = threading.Lock()

    # -- registration ----------------------------------------------------------

    def connect(
        self,
        receiver: Callable[..., Any],
        dispatch_uid: Any = None,
        weak: bool = True,
    ) -> None:
        """Register ``receiver``; ``dispatch_uid`` de-duplicates connections."""
        key = dispatch_uid if dispatch_uid is not None else id(receiver)
        ref: Callable[..., Any]
        if weak:
            try:
                ref = weakref.ref(receiver)
            except TypeError:
                ref = receiver  # not weakref-able (e.g. builtins, C callables)
        else:
            ref = receiver
        with self._lock:
            self._receivers = [(k, r) for k, r in self._receivers if k != key]
            self._receivers.append((key, ref))

    def disconnect(self, receiver: Callable[..., Any] | None = None, dispatch_uid: Any = None) -> bool:
        """Unregister; returns True if a receiver was removed."""
        key = dispatch_uid if dispatch_uid is not None else (id(receiver) if receiver else None)
        if key is None:
            return False
        with self._lock:
            before = len(self._receivers)
            self._receivers = [(k, r) for k, r in self._receivers if k != key]
            return len(self._receivers) < before

    # -- dispatch ---------------------------------------------------------------

    def _live_receivers(self) -> list[Callable[..., Any]]:
        out: list[Callable[..., Any]] = []
        with self._lock:
            snapshot = list(self._receivers)
        dead: list[Any] = []
        for key, ref in snapshot:
            target = ref() if isinstance(ref, weakref.ref) else ref
            if target is None:
                dead.append(key)
            else:
                out.append(target)
        if dead:
            with self._lock:
                self._receivers = [(k, r) for k, r in self._receivers if k not in dead]
        return out

    def send(self, sender: Any = None, **kwargs: Any) -> list[tuple[Callable[..., Any], Any]]:
        """Invoke all receivers; raises on the first receiver error."""
        return [(r, r(sender=sender, **kwargs)) for r in self._live_receivers()]

    def send_robust(self, sender: Any = None, **kwargs: Any) -> list[tuple[Callable[..., Any], Any]]:
        """Like send() but catches per-receiver errors, returning them as results."""
        responses: list[tuple[Callable[..., Any], Any]] = []
        for receiver in self._live_receivers():
            try:
                responses.append((receiver, receiver(sender=sender, **kwargs)))
            except Exception as err:
                responses.append((receiver, err))
        return responses

    def has_listeners(self) -> bool:
        return bool(self._live_receivers())


# -- Built-in signals -----------------------------------------------------------

request_started = Signal()  # sent by the app factory when a request begins
request_finished = Signal()  # sent by the app factory when a response ships
setting_changed = Signal()  # sent by override_settings: setting=, value=, enter=
