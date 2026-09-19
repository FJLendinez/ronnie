"""Tests for the signal dispatcher (Fase 2)."""

from __future__ import annotations

import gc

from ronnie.core.signals import Signal


def _append(value, calls):
    def receiver(sender, **kw):
        calls.append(value)

    return receiver


class TestSignal:
    def test_send_calls_receivers_with_sender_and_kwargs(self):
        sig, seen = Signal(), []

        def receiver(sender, **kw):
            seen.append((sender, kw.get("value")))
            return "ok"

        sig.connect(receiver, weak=False)
        responses = sig.send(sender="obj", value=42)
        assert seen == [("obj", 42)]
        assert responses == [(receiver, "ok")]

    def test_multiple_receivers_in_order(self):
        sig, calls = Signal(), []
        sig.connect(_append("a", calls), weak=False)
        sig.connect(_append("b", calls), weak=False)
        sig.send()
        assert calls == ["a", "b"]

    def test_dispatch_uid_deduplicates(self):
        sig, calls = Signal(), []
        receiver = _append(1, calls)
        sig.connect(receiver, dispatch_uid="x")
        sig.connect(receiver, dispatch_uid="x")
        sig.send()
        assert calls == [1]

    def test_disconnect_by_uid(self):
        sig, calls = Signal(), []
        sig.connect(_append(1, calls), dispatch_uid="x")
        assert sig.disconnect(dispatch_uid="x") is True
        assert sig.disconnect(dispatch_uid="x") is False
        sig.send()
        assert calls == []

    def test_send_robust_collects_errors(self):
        sig = Signal()

        def boom(sender, **kw):
            raise ValueError("boom")

        def ok(sender, **kw):
            return "fine"

        sig.connect(boom, weak=False)
        sig.connect(ok, weak=False)
        responses = sig.send_robust()
        assert isinstance(responses[0][1], ValueError)
        assert responses[1][1] == "fine"

    def test_send_propagates_errors(self):
        sig = Signal()

        def boom(sender, **kw):
            raise ValueError("x")

        sig.connect(boom, weak=False)
        try:
            sig.send()
        except ValueError:
            pass  # expected
        else:
            raise AssertionError("send() should propagate receiver errors")

    def test_weak_refs_are_dropped(self):
        sig = Signal()

        def receiver(sender, **kw):
            return 1

        sig.connect(receiver)  # weak by default, like django.dispatch
        del receiver
        gc.collect()
        assert sig.has_listeners() is False

    def test_has_listeners(self):
        sig = Signal()
        assert sig.has_listeners() is False
        receiver = _append(None, [])
        sig.connect(receiver)
        try:
            assert sig.has_listeners() is True
        finally:
            sig.disconnect(dispatch_uid=id(receiver))
