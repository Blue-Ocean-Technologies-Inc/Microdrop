"""End-to-end test for the RoutesHandler chain against a real broker.

Flow exercised:
  RoutesHandler.on_step → publish_message(ELECTRODES_STATE_CHANGE)
                       → message_router → demo electrode_responder
                       → publish_message(ELECTRODES_STATE_APPLIED)
                       → message_router → executor_listener
                       → mailbox → ctx.wait_for() returns
                       → next phase
"""

import json
import threading
import time

import dramatiq
import pytest
from dramatiq import Worker
from pyface.qt.QtCore import Qt

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.builtins.duration_column import (
    make_duration_column,
)
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.linear_repeats_column import (
    make_linear_repeats_column,
)
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repeat_duration_column import (
    make_repeat_duration_column,
)
from pluggable_protocol_tree.builtins.repetitions_column import (
    make_repetitions_column,
)
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.soft_end_column import make_soft_end_column
from pluggable_protocol_tree.builtins.soft_start_column import (
    make_soft_start_column,
)
from pluggable_protocol_tree.builtins.trail_length_column import (
    make_trail_length_column,
)
from pluggable_protocol_tree.builtins.trail_overlay_column import (
    make_trail_overlay_column,
)
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.demos.electrode_responder import (
    DEMO_RESPONDER_ACTOR_NAME,
)
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.signals import ExecutorSignals
# Importing the listener module registers its dramatiq actor.
from pluggable_protocol_tree.execution import listener as _listener  # noqa
from pluggable_protocol_tree.models.row_manager import RowManager


PHASE_SPY_ACTOR_NAME = "ppt_test_phase_spy"
_phase_spy_log: list = []


@dramatiq.actor(actor_name=PHASE_SPY_ACTOR_NAME, queue_name="default")
def _phase_spy(message: str, topic: str, timestamp: float = None):
    """Records every ELECTRODES_STATE_CHANGE for assertion."""
    _phase_spy_log.append(json.loads(message))


def _all_columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_trail_length_column(), make_trail_overlay_column(),
        make_soft_start_column(), make_soft_end_column(),
        make_repeat_duration_column(), make_linear_repeats_column(),
    ]


def test_routes_handler_publishes_phases_and_unblocks_on_ack(router_actor):
    """One step with electrodes=['e00','e01'] + routes=[['e02','e03','e04']]
    + trail_length=1 → 3 phases, each unioned with the static set,
    each ack'd by the demo electrode_responder."""
    _phase_spy_log.clear()

    # Subscribe responder + listener + spy.
    subs = (
        (ELECTRODES_STATE_CHANGE, DEMO_RESPONDER_ACTOR_NAME),
        (ELECTRODES_STATE_APPLIED,
         "pluggable_protocol_tree_executor_listener"),
        (ELECTRODES_STATE_CHANGE, PHASE_SPY_ACTOR_NAME),
    )
    for topic, actor_name in subs:
        try:
            router_actor.message_router_data.remove_subscriber_from_topic(
                topic=topic, subscribing_actor_name=actor_name,
            )
        except Exception:
            pass
        router_actor.message_router_data.add_subscriber_to_topic(
            topic=topic, subscribing_actor_name=actor_name,
        )

    broker = dramatiq.get_broker()
    broker.flush_all()
    try:
        cols = _all_columns()
        rm = RowManager(columns=cols)
        rm.protocol_metadata["electrode_to_channel"] = {
            f"e{i:02d}": i for i in range(25)
        }
        rm.add_step(values={
            "name": "S",
            "duration_s": 0.1,    # short dwell so total test stays fast
            "electrodes": ["e00", "e01"],
            "routes": [["e02", "e03", "e04"]],
            "trail_length": 1,
            "trail_overlay": 0,
        })

        ex = ProtocolExecutor(
            row_manager=rm,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )
        finished = threading.Event()
        ex.qsignals.protocol_finished.connect(
            finished.set, type=Qt.DirectConnection,
        )

        worker = Worker(broker, worker_timeout=100)
        worker.start()
        try:
            ex.start()
            assert finished.wait(timeout=15.0), \
                "protocol_finished did not fire within 15s"
            ex.wait(timeout=2.0)
        finally:
            worker.stop()

        # 3 phases — one per route position.
        assert len(_phase_spy_log) == 3, f"phases: {_phase_spy_log!r}"
        # Each phase = static ∪ {single route electrode}.
        assert _phase_spy_log[0]["electrodes"] == ["e00", "e01", "e02"]
        assert _phase_spy_log[1]["electrodes"] == ["e00", "e01", "e03"]
        assert _phase_spy_log[2]["electrodes"] == ["e00", "e01", "e04"]
        # Channel resolution from the seeded mapping.
        assert _phase_spy_log[0]["channels"] == [0, 1, 2]
        assert _phase_spy_log[1]["channels"] == [0, 1, 3]
        assert _phase_spy_log[2]["channels"] == [0, 1, 4]
    finally:
        for topic, actor_name in subs:
            try:
                router_actor.message_router_data.remove_subscriber_from_topic(
                    topic=topic, subscribing_actor_name=actor_name,
                )
            except Exception:
                pass
