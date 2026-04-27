"""End-to-end test: a protocol with voltage/frequency + electrodes
runs against an in-process responder, and the priority-20 acks land
strictly before any priority-30 electrode publish.

Requires a running Redis server on localhost:6379.
"""
import time
from threading import Lock

import dramatiq
import pytest

# Strip Prometheus middleware before importing anything that uses the broker.
for _m in list(dramatiq.get_broker().middleware):
    if _m.__module__ == "dramatiq.middleware.prometheus":
        dramatiq.get_broker().middleware.remove(_m)

from pluggable_protocol_tree.builtins.duration_column import (
    make_duration_column,
)
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repetitions_column import (
    make_repetitions_column,
)
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.models.row_manager import RowManager

from dropbot_controller.consts import (
    PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY,
    VOLTAGE_APPLIED, FREQUENCY_APPLIED,
)
from dropbot_protocol_controls.protocol_columns.voltage_column import (
    make_voltage_column,
)
from dropbot_protocol_controls.protocol_columns.frequency_column import (
    make_frequency_column,
)


# Recording spy actor — captures every relevant topic with timestamps
# so we can assert on ordering.
EVENT_LOG = []
EVENT_LOG_LOCK = Lock()
SPY_ACTOR_NAME = "test_ppt4_round_trip_spy"


@dramatiq.actor(actor_name=SPY_ACTOR_NAME, queue_name="default")
def _record_event(message: str, topic: str, timestamp: float = None):
    with EVENT_LOG_LOCK:
        EVENT_LOG.append((time.monotonic(), topic, message))


@pytest.fixture
def setup_responder_and_spy(router_actor):
    """Subscribe the voltage/frequency demo responder + electrode
    responder + spy; clean up after."""
    from dramatiq import Worker

    EVENT_LOG.clear()

    # Importing these modules registers their actors with the broker.
    from dropbot_protocol_controls.demos.voltage_frequency_responder import (
        subscribe_demo_responder,
    )
    # Importing the listener registers the executor_listener actor.
    from pluggable_protocol_tree.execution import listener as _listener  # noqa: F401
    from pluggable_protocol_tree.demos.electrode_responder import (
        DEMO_RESPONDER_ACTOR_NAME,
    )

    broker = dramatiq.get_broker()
    broker.flush_all()

    router = router_actor

    # Voltage/frequency responder + executor listener (turnkey helper).
    subscribe_demo_responder(router)

    # Electrode responder + executor listener for ELECTRODES_STATE_APPLIED
    # — _setup_demo_hardware would do this for us if we used ProtocolSession,
    # but this test drives the executor directly so we wire it manually.
    router.message_router_data.add_subscriber_to_topic(
        topic=ELECTRODES_STATE_CHANGE,
        subscribing_actor_name=DEMO_RESPONDER_ACTOR_NAME,
    )
    router.message_router_data.add_subscriber_to_topic(
        topic=ELECTRODES_STATE_APPLIED,
        subscribing_actor_name="pluggable_protocol_tree_executor_listener",
    )

    # Spy on the topics we want to assert ordering on.
    for topic in (PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY,
                  VOLTAGE_APPLIED, FREQUENCY_APPLIED,
                  ELECTRODES_STATE_CHANGE):
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
        for topic in (PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY,
                      VOLTAGE_APPLIED, FREQUENCY_APPLIED,
                      ELECTRODES_STATE_CHANGE):
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
        for topic in (PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY):
            router.message_router_data.remove_subscriber_from_topic(
                topic=topic,
                subscribing_actor_name="ppt_demo_voltage_frequency_responder",
            )
        for topic in (VOLTAGE_APPLIED, FREQUENCY_APPLIED):
            router.message_router_data.remove_subscriber_from_topic(
                topic=topic,
                subscribing_actor_name="pluggable_protocol_tree_executor_listener",
            )


def _build_columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_voltage_column(), make_frequency_column(),
    ]


def test_voltage_frequency_acks_before_electrode_change(setup_responder_and_spy):
    """Both _APPLIED acks must land before any ELECTRODES_STATE_CHANGE
    publish — proves priority 20 < priority 30 in practice."""
    rm = RowManager(columns=_build_columns())
    rm.protocol_metadata["electrode_to_channel"] = {f"e{i:02d}": i for i in range(5)}
    rm.add_step(values={
        "name": "S1",
        "duration_s": 0.05,
        "electrodes": ["e00", "e01"],
        "voltage": 120,
        "frequency": 5000,
    })

    executor = ProtocolExecutor(row_manager=rm)
    executor.start()
    finished = executor.wait(timeout=15.0)
    assert finished, "Executor did not finish within 15s"

    # Find the timestamps of voltage/frequency acks and the first electrode change.
    with EVENT_LOG_LOCK:
        events = list(EVENT_LOG)

    def first_t(topic):
        for t, top, _ in events:
            if top == topic:
                return t
        return None

    t_v_ack = first_t(VOLTAGE_APPLIED)
    t_f_ack = first_t(FREQUENCY_APPLIED)
    t_e_change = first_t(ELECTRODES_STATE_CHANGE)

    assert t_v_ack is not None, f"No VOLTAGE_APPLIED ack received. Events: {events}"
    assert t_f_ack is not None, f"No FREQUENCY_APPLIED ack received. Events: {events}"
    assert t_e_change is not None, f"No ELECTRODES_STATE_CHANGE seen. Events: {events}"

    assert t_v_ack < t_e_change, (
        f"Voltage ack ({t_v_ack}) should land before electrode change ({t_e_change})"
    )
    assert t_f_ack < t_e_change, (
        f"Frequency ack ({t_f_ack}) should land before electrode change ({t_e_change})"
    )


def test_responder_received_correct_setpoints(setup_responder_and_spy):
    """The protocol writes voltage=120 and frequency=5000; the request
    publishes must carry those exact values."""
    rm = RowManager(columns=_build_columns())
    rm.protocol_metadata["electrode_to_channel"] = {"e00": 0}
    rm.add_step(values={
        "name": "S1",
        "duration_s": 0.05,
        "electrodes": ["e00"],
        "voltage": 120,
        "frequency": 5000,
    })

    executor = ProtocolExecutor(row_manager=rm)
    executor.start()
    finished = executor.wait(timeout=15.0)
    assert finished

    with EVENT_LOG_LOCK:
        events = list(EVENT_LOG)

    voltage_msgs = [m for _, t, m in events if t == PROTOCOL_SET_VOLTAGE]
    frequency_msgs = [m for _, t, m in events if t == PROTOCOL_SET_FREQUENCY]
    assert "120" in voltage_msgs
    assert "5000" in frequency_msgs
