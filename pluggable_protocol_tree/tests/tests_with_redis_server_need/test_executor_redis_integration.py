"""End-to-end test for the executor's Dramatiq round-trip.

Skips automatically if Redis isn't reachable (see conftest.py).

Proves: publish_message → message_router_actor → executor_listener actor
→ route_to_active_step → mailbox → ctx.wait_for → handler returns the
payload (as a JSON string — that's the wire format, handlers JSON-decode
on the receiving side).
"""

import json
import threading
import time

import dramatiq
from dramatiq import Worker

from microdrop_utils.dramatiq_pub_sub_helpers import (
    MessageRouterActor, MessageRouterData, publish_message,
)
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.signals import ExecutorSignals
# Importing the listener module registers the Dramatiq actor.
from pluggable_protocol_tree.execution import listener  # noqa: F401
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.columns.readonly_label import (
    ReadOnlyLabelColumnView,
)


ACK_TOPIC = "pluggable_protocol_tree/test/ack"


def test_publish_then_wait_for_round_trips_via_real_dramatiq(router_actor):
    """A handler publishes a request and then waits for an ack on the
    same topic the message router routes back to the executor's
    listener. Worker context manager runs the message_router_actor and
    executor_listener actors in the background while the executor's
    on_step blocks on ctx.wait_for."""
    received = []

    class _AckHandler(BaseColumnHandler):
        wait_for_topics = [ACK_TOPIC]

        def on_step(self, row, ctx):
            # Publish the ack ourselves (in a real handler this would
            # publish a request and a different actor would publish the
            # ack — here we drive both halves to keep the test self-
            # contained while still exercising the round-trip).
            payload_out = json.dumps({"step_uuid": row.uuid, "ok": True})
            publish_message(message=payload_out, topic=ACK_TOPIC)
            payload_in = ctx.wait_for(ACK_TOPIC, timeout=5.0)
            received.append(payload_in)

    ack_col = Column(
        model=BaseColumnModel(col_id="ack", col_name="Ack", default_value=None),
        view=ReadOnlyLabelColumnView(),
        handler=_AckHandler(),
    )

    # Add the subscription for ACK_TOPIC against the session-shared
    # router_actor (the plugin's start() does this in production).
    router_actor.message_router_data.add_subscriber_to_topic(
        topic=ACK_TOPIC,
        subscribing_actor_name="pluggable_protocol_tree_executor_listener",
    )

    broker = dramatiq.get_broker()
    broker.flush_all()
    try:
        cols = [make_type_column(), make_id_column(), make_name_column(),
                make_repetitions_column(), make_duration_column(), ack_col]
        rm = RowManager(columns=cols)
        rm.add_step(values={"name": "S"})
        ex = ProtocolExecutor(
            row_manager=rm,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )

        # Start a Dramatiq worker so message_router_actor and
        # executor_listener actually fire. Without this, publishes go
        # into Redis but never get consumed, so wait_for would time out.
        worker = Worker(broker, worker_timeout=100)
        worker.start()
        try:
            runner = threading.Thread(target=ex.run, daemon=True)
            runner.start()
            runner.join(timeout=10.0)
            assert not runner.is_alive(), "executor.run did not return in 10s"
        finally:
            worker.stop()

        assert len(received) == 1, f"expected 1 received message, got {len(received)}"
        # Listener delivers the raw string from message_router; decode here.
        payload = json.loads(received[0])
        assert payload["ok"] is True
        assert payload["step_uuid"] == rm.root.children[0].uuid

    finally:
        router_actor.message_router_data.remove_subscriber_from_topic(
            topic=ACK_TOPIC,
            subscribing_actor_name="pluggable_protocol_tree_executor_listener",
        )


# --- realistic two-actor protocol flow test ----------------------------

REQUEST_TOPIC = "pluggable_protocol_tree/test/state_request"
APPLIED_TOPIC = "pluggable_protocol_tree/test/state_applied"

# Module-level so registration happens once when the test module is
# imported (the conftest configures the broker before this runs).
# Mutable state lives on a fresh list per test (cleared in setup).
_responder_log: list = []
ACK_DELAY_S = 0.30


@dramatiq.actor(
    actor_name="ppt_test_state_responder",
    queue_name="default",
)
def _state_responder(message: str, topic: str, timestamp: float = None):
    """Simulates a hardware controller that takes ACK_DELAY_S to apply
    state and then publishes a confirmation."""
    import time as _t
    _responder_log.append(("received", _t.monotonic()))
    _t.sleep(ACK_DELAY_S)
    publish_message(message="ok", topic=APPLIED_TOPIC)
    _responder_log.append(("published_ack", _t.monotonic()))


def test_step_blocks_on_state_apply_before_duration_starts(router_actor):
    """End-to-end protocol-flow test:

    A column's on_step publishes a 'set state' request and waits for an
    asynchronous 'state applied' confirmation from another actor. Only
    once the confirmation arrives may the next priority bucket
    (DurationColumnHandler at priority 90) start its dwell sleep.

    Proves:
      * publish_message → message_router → subscriber actor → router →
        executor_listener → mailbox → ctx.wait_for round-trip works
        end-to-end against a real broker.
      * Priority buckets serialize correctly: state-apply (priority 30)
        finishes BEFORE the duration sleep (priority 90) starts —
        observable as step duration ≈ ack_delay + duration_s, not
        max(ack_delay, duration_s).
      * The protocol stays on the active step the entire time (no
        premature step_finished while wait_for is blocked).
    """
    from pyface.qt.QtCore import Qt
    DURATION_S = 0.40

    _responder_log.clear()
    handler_events: list = []

    class _ApplyStateHandler(BaseColumnHandler):
        # Priority 30 puts this in a strictly earlier bucket than
        # DurationColumnHandler's 90 — so they MUST run sequentially,
        # not in parallel.
        priority = 30
        wait_for_topics = [APPLIED_TOPIC]

        def on_step(self, row, ctx):
            handler_events.append(("publish_request", time.monotonic()))
            publish_message(message="set_state", topic=REQUEST_TOPIC)
            payload = ctx.wait_for(APPLIED_TOPIC, timeout=5.0)
            handler_events.append(("got_ack", time.monotonic(), payload))

    apply_col = Column(
        model=BaseColumnModel(
            col_id="apply", col_name="Apply", default_value=None,
        ),
        view=ReadOnlyLabelColumnView(),
        handler=_ApplyStateHandler(),
    )

    router_actor.message_router_data.add_subscriber_to_topic(
        topic=REQUEST_TOPIC,
        subscribing_actor_name="ppt_test_state_responder",
    )
    router_actor.message_router_data.add_subscriber_to_topic(
        topic=APPLIED_TOPIC,
        subscribing_actor_name="pluggable_protocol_tree_executor_listener",
    )

    broker = dramatiq.get_broker()
    broker.flush_all()
    try:
        cols = [
            make_type_column(), make_id_column(), make_name_column(),
            make_repetitions_column(), make_duration_column(), apply_col,
        ]
        rm = RowManager(columns=cols)
        rm.add_step(values={"name": "S", "duration_s": DURATION_S})
        ex = ProtocolExecutor(
            row_manager=rm,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )

        # Capture step boundaries via Qt signals. DirectConnection so
        # the slot fires synchronously on the worker thread without
        # needing a QApplication event loop.
        timing: dict = {}
        ex.qsignals.step_started.connect(
            lambda r: timing.update(step_started=time.monotonic()),
            type=Qt.DirectConnection,
        )
        ex.qsignals.step_finished.connect(
            lambda r: timing.update(step_finished=time.monotonic()),
            type=Qt.DirectConnection,
        )

        worker = Worker(broker, worker_timeout=100)
        worker.start()
        try:
            runner = threading.Thread(target=ex.run, daemon=True)
            runner.start()
            runner.join(timeout=15.0)
            assert not runner.is_alive(), "executor.run did not return"
        finally:
            worker.stop()

        # --- assertions ----------------------------------------------

        assert "step_started" in timing, "step_started signal didn't fire"
        assert "step_finished" in timing, "step_finished signal didn't fire"
        step_elapsed = timing["step_finished"] - timing["step_started"]

        # The handler ran in the right order: publish, then ack.
        publish_t = next(t for e, t in
                         ((e[0], e[1]) for e in handler_events)
                         if e == "publish_request")
        ack_t = next(t for e, t in
                     ((e[0], e[1]) for e in handler_events)
                     if e == "got_ack")
        ack_elapsed = ack_t - publish_t

        # The responder also ran end-to-end.
        assert ("received", ) == tuple(e[0] for e in _responder_log[:1]), \
            f"responder didn't receive request; log={_responder_log!r}"
        assert "published_ack" in [e[0] for e in _responder_log], \
            f"responder didn't publish ack; log={_responder_log!r}"

        # Ack arrived AT LEAST ACK_DELAY_S after the request — the
        # responder slept that long. Allow 10% slack.
        assert ack_elapsed >= ACK_DELAY_S * 0.9, (
            f"ack arrived too fast: {ack_elapsed:.3f}s "
            f"< expected ~{ACK_DELAY_S}s"
        )

        # The whole step took ack_delay + duration_s — NOT max() of
        # them. If the duration sleep had started in parallel with
        # the wait_for, step would have taken ~max(ACK_DELAY,
        # DURATION) ~= 0.4s. Sequential is ~0.7s.
        expected_min = ACK_DELAY_S + DURATION_S
        assert step_elapsed >= expected_min * 0.9, (
            f"step took {step_elapsed:.3f}s; expected >= "
            f"{expected_min:.3f}s (ack {ACK_DELAY_S}s + dwell {DURATION_S}s). "
            f"Did the duration sleep start in parallel with wait_for?"
        )
        # Sanity: not wildly longer than expected (allow 0.5s overhead).
        assert step_elapsed < expected_min + 0.5, (
            f"step took {step_elapsed:.3f}s; expected ~{expected_min:.3f}s "
            f"(too much overhead — broker / worker contention?)"
        )

    finally:
        router_actor.message_router_data.remove_subscriber_from_topic(
            topic=REQUEST_TOPIC,
            subscribing_actor_name="ppt_test_state_responder",
        )
        router_actor.message_router_data.remove_subscriber_from_topic(
            topic=APPLIED_TOPIC,
            subscribing_actor_name="pluggable_protocol_tree_executor_listener",
        )
