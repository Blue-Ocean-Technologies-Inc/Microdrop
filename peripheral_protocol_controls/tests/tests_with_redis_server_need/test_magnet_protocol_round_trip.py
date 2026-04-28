"""End-to-end test: a protocol with magnet + electrodes runs against
the in-process magnet responder, and the priority-20 ack lands
strictly before any priority-30 electrode publish.

Requires a running Redis server on localhost:6379.
"""
import json
import time
from threading import Lock

import dramatiq
import pytest

# Strip Prometheus middleware before importing anything that uses the broker.
from microdrop_utils.broker_server_helpers import (
    remove_middleware_from_dramatiq_broker,
)
remove_middleware_from_dramatiq_broker(
    middleware_name="dramatiq.middleware.prometheus",
    broker=dramatiq.get_broker(),
)

from peripheral_controller.consts import (
    PROTOCOL_SET_MAGNET, MAGNET_APPLIED,
)
from peripheral_protocol_controls.protocol_columns.magnet_column import (
    make_magnet_column,
)
from pluggable_protocol_tree.builtins.duration_column import (
    make_duration_column,
)
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
from pluggable_protocol_tree.models.row_manager import RowManager


# Recording spy actor — captures every relevant topic with timestamps
# so we can assert ordering.
EVENT_LOG = []
EVENT_LOG_LOCK = Lock()
SPY_ACTOR_NAME = "test_ppt5_magnet_round_trip_spy"


@dramatiq.actor(actor_name=SPY_ACTOR_NAME, queue_name="default")
def _record_event(message: str, topic: str, timestamp: float = None):
    with EVENT_LOG_LOCK:
        EVENT_LOG.append((time.monotonic(), topic, message))


@pytest.fixture
def setup_responder_and_spy(router_actor):
    """Subscribe the magnet demo responder + electrode responder + spy;
    clean up after."""
    from dramatiq import Worker

    EVENT_LOG.clear()

    # Importing these modules registers their actors with the broker.
    from peripheral_protocol_controls.demos.magnet_responder import (
        subscribe_demo_responder, DEMO_MAGNET_RESPONDER_ACTOR_NAME,
    )
    from pluggable_protocol_tree.execution import listener as _listener  # noqa: F401
    from pluggable_protocol_tree.demos.electrode_responder import (
        DEMO_RESPONDER_ACTOR_NAME,
    )

    broker = dramatiq.get_broker()
    broker.flush_all()

    router = router_actor

    # Magnet responder + executor listener (turnkey helper)
    subscribe_demo_responder(router)

    # Electrode responder + executor listener for ELECTRODES_STATE_APPLIED
    router.message_router_data.add_subscriber_to_topic(
        topic=ELECTRODES_STATE_CHANGE,
        subscribing_actor_name=DEMO_RESPONDER_ACTOR_NAME,
    )
    router.message_router_data.add_subscriber_to_topic(
        topic=ELECTRODES_STATE_APPLIED,
        subscribing_actor_name="pluggable_protocol_tree_executor_listener",
    )

    # Spy on the topics we want to assert on
    for topic in (PROTOCOL_SET_MAGNET, MAGNET_APPLIED, ELECTRODES_STATE_CHANGE):
        router.message_router_data.add_subscriber_to_topic(
            topic=topic, subscribing_actor_name=SPY_ACTOR_NAME,
        )

    worker = Worker(broker, worker_timeout=100)
    worker.start()
    try:
        yield router
    finally:
        worker.stop()
        # Clean up subscriptions so they don't bleed into the next test.
        for topic in (PROTOCOL_SET_MAGNET, MAGNET_APPLIED, ELECTRODES_STATE_CHANGE):
            router.message_router_data.remove_subscriber_from_topic(
                topic=topic, subscribing_actor_name=SPY_ACTOR_NAME,
            )
        router.message_router_data.remove_subscriber_from_topic(
            topic=ELECTRODES_STATE_CHANGE,
            subscribing_actor_name=DEMO_RESPONDER_ACTOR_NAME,
        )
        router.message_router_data.remove_subscriber_from_topic(
            topic=ELECTRODES_STATE_APPLIED,
            subscribing_actor_name="pluggable_protocol_tree_executor_listener",
        )
        from peripheral_protocol_controls.demos.magnet_responder import (
            DEMO_MAGNET_RESPONDER_ACTOR_NAME, EXECUTOR_LISTENER_ACTOR_NAME,
        )
        router.message_router_data.remove_subscriber_from_topic(
            topic=PROTOCOL_SET_MAGNET,
            subscribing_actor_name=DEMO_MAGNET_RESPONDER_ACTOR_NAME,
        )
        router.message_router_data.remove_subscriber_from_topic(
            topic=MAGNET_APPLIED,
            subscribing_actor_name=EXECUTOR_LISTENER_ACTOR_NAME,
        )


def _build_columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        *_expand_compound(make_magnet_column()),
    ]


def test_magnet_responder_received_correct_setpoint(setup_responder_and_spy):
    """The protocol writes magnet=on/height=5.0; responder sees that JSON."""
    rm = RowManager(columns=_build_columns())
    rm.protocol_metadata["electrode_to_channel"] = {"e00": 0}
    rm.add_step(values={
        "name": "S1",
        "duration_s": 0.05,
        "electrodes": ["e00"],
        "magnet_on": True,
        "magnet_height_mm": 5.0,
    })

    executor = ProtocolExecutor(row_manager=rm)
    executor.start()
    finished = executor.wait(timeout=15.0)
    assert finished, "Executor did not finish within 15s"

    with EVENT_LOG_LOCK:
        events = list(EVENT_LOG)

    magnet_msgs = [m for _, t, m in events if t == PROTOCOL_SET_MAGNET]
    assert len(magnet_msgs) >= 1
    payload = json.loads(magnet_msgs[0])
    assert payload == {"on": True, "height_mm": 5.0}


def test_magnet_ack_before_electrode_change(setup_responder_and_spy):
    """MAGNET_APPLIED ack must land before any ELECTRODES_STATE_CHANGE
    publish — proves priority 20 < priority 30 in practice."""
    rm = RowManager(columns=_build_columns())
    rm.protocol_metadata["electrode_to_channel"] = {f"e{i:02d}": i for i in range(5)}
    rm.add_step(values={
        "name": "S1",
        "duration_s": 0.05,
        "electrodes": ["e00", "e01"],
        "magnet_on": True,
        "magnet_height_mm": 5.0,
    })

    executor = ProtocolExecutor(row_manager=rm)
    executor.start()
    finished = executor.wait(timeout=15.0)
    assert finished

    with EVENT_LOG_LOCK:
        events = list(EVENT_LOG)

    def first_t(topic):
        for t, top, _ in events:
            if top == topic:
                return t
        return None

    t_magnet_ack = first_t(MAGNET_APPLIED)
    t_e_change = first_t(ELECTRODES_STATE_CHANGE)

    assert t_magnet_ack is not None, f"No MAGNET_APPLIED ack received. Events: {events}"
    assert t_e_change is not None, f"No ELECTRODES_STATE_CHANGE seen. Events: {events}"

    assert t_magnet_ack < t_e_change, (
        f"Magnet ack ({t_magnet_ack}) should land before electrode "
        f"change ({t_e_change})"
    )
