"""End-to-end test for the executor's Dramatiq round-trip.

Skips automatically if Redis isn't reachable. Run via:

    redis-server &              # in another shell
    cd microdrop-py && pixi run bash -c \\
      "cd src && pytest pluggable_protocol_tree/tests/tests_with_redis_server_need/ -v"
"""

import threading
import time

import pytest


def _redis_available() -> bool:
    try:
        import dramatiq
        broker = dramatiq.get_broker()
        broker.client.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(),
    reason="Redis broker not reachable",
)


def test_publish_then_wait_for_round_trips_via_real_dramatiq():
    """A handler publishes a request and then waits for an ack on the
    same topic the message router routes back to the executor's
    listener. Proves: publish → broker → executor_listener actor →
    route_to_active_step → mailbox → wait_for → handler returns the
    payload."""
    from microdrop_utils.dramatiq_pub_sub_helpers import (
        MessageRouterData, publish_message,
    )
    from pluggable_protocol_tree.builtins.duration_column import make_duration_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.execution.events import PauseEvent
    from pluggable_protocol_tree.execution.executor import ProtocolExecutor
    from pluggable_protocol_tree.execution.signals import ExecutorSignals
    from pluggable_protocol_tree.models.column import (
        BaseColumnHandler, BaseColumnModel, Column,
    )
    from pluggable_protocol_tree.models.row_manager import RowManager
    from pluggable_protocol_tree.views.columns.readonly_label import (
        ReadOnlyLabelColumnView,
    )

    ACK_TOPIC = "pluggable_protocol_tree/test/ack"
    received = []

    class _AckHandler(BaseColumnHandler):
        wait_for_topics = [ACK_TOPIC]

        def on_step(self, row, ctx):
            # Publish the ack ourselves (in a real handler this would
            # publish a request and a different actor would publish the
            # ack). The point is to prove the mailbox round-trips.
            publish_message(
                topic=ACK_TOPIC, message={"step_uuid": row.uuid, "ok": True},
            )
            payload = ctx.wait_for(ACK_TOPIC, timeout=5.0)
            received.append(payload)

    ack_col = Column(
        model=BaseColumnModel(col_id="ack", col_name="Ack", default_value=None),
        view=ReadOnlyLabelColumnView(),
        handler=_AckHandler(),
    )

    # Register the executor listener's subscription for ACK_TOPIC. (The
    # plugin's start() does this in production; we do it inline here.)
    router_data = MessageRouterData()
    router_data.add_subscriber_to_topic(
        topic=ACK_TOPIC,
        subscribing_actor_name="pluggable_protocol_tree_executor_listener",
    )
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

        # Run on a worker thread so dramatiq has time to deliver while
        # the main thread monitors. (Unit tests call ex.run() directly;
        # here we exercise the same code path but with the broker live.)
        runner = threading.Thread(target=ex.run, daemon=True)
        runner.start()
        runner.join(timeout=10.0)

        assert not runner.is_alive(), "executor.run did not return in 10s"
        assert len(received) == 1
        assert received[0]["ok"] is True
        assert received[0]["step_uuid"] == rm.root.children[0].uuid

    finally:
        router_data.remove_subscriber_from_topic(
            topic=ACK_TOPIC,
            subscribing_actor_name="pluggable_protocol_tree_executor_listener",
        )
