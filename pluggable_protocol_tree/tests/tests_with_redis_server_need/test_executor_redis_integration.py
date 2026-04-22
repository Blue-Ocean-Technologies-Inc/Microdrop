"""End-to-end test for the executor's Dramatiq round-trip.

Skips automatically if Redis isn't reachable (see conftest.py).

Proves: publish_message → message_router_actor → executor_listener actor
→ route_to_active_step → mailbox → ctx.wait_for → handler returns the
payload (as a JSON string — that's the wire format, handlers JSON-decode
on the receiving side).
"""

import json
import threading

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


def test_publish_then_wait_for_round_trips_via_real_dramatiq():
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

    # Instantiate the message router actor (registers its Dramatiq
    # actor) and add the subscription for ACK_TOPIC. The plugin's
    # start() does this in production.
    router_actor = MessageRouterActor()
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
