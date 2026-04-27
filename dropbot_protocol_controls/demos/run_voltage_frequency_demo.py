"""Runnable demo for the dropbot_protocol_controls voltage/frequency columns.

Builds a protocol with voltage + frequency columns alongside the
PPT-3 builtins, opens a ProtocolSession with demo hardware, subscribes
the voltage/frequency demo responder, and runs end-to-end.

This is the script a developer runs to manually verify the new plugin
without the full GUI app and without real hardware.

Run: pixi run python -m dropbot_protocol_controls.demos.run_voltage_frequency_demo
"""

import json
import logging
import sys
import tempfile
import time
from pathlib import Path

import dramatiq

# Strip Prometheus middleware (matches the other demos); without this,
# every actor publish raises inside its after_process_message hook.
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
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.repetitions_column import (
    make_repetitions_column,
)
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.session import ProtocolSession

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
from dropbot_protocol_controls.demos.voltage_frequency_responder import (
    subscribe_demo_responder,
)


logger = logging.getLogger(__name__)

# Spy that prints every voltage/frequency publish + ack so the demo
# output is interpretable.
SPY_ACTOR_NAME = "ppt_vf_demo_spy"


@dramatiq.actor(actor_name=SPY_ACTOR_NAME, queue_name="default")
def _vf_spy(message: str, topic: str, timestamp: float = None):
    print(f"  vf-spy: {topic} = {message}", flush=True)


def _build_sample_protocol_file(path: Path) -> None:
    """3-step protocol exercising voltage + frequency + electrodes."""
    cols = [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_voltage_column(), make_frequency_column(),
    ]
    rm = RowManager(columns=cols)
    rm.protocol_metadata["electrode_to_channel"] = {
        f"e{i:02d}": i for i in range(10)
    }
    rm.add_step(values={
        "name": "Hold pad with 100V/10kHz",
        "duration_s": 0.2,
        "electrodes": ["e00", "e01"],
        "voltage": 100,
        "frequency": 10000,
    })
    rm.add_step(values={
        "name": "Switch to 120V/5kHz",
        "duration_s": 0.2,
        "electrodes": ["e02", "e03"],
        "voltage": 120,
        "frequency": 5000,
    })
    rm.add_step(values={
        "name": "Cooldown 75V/1kHz",
        "duration_s": 0.2,
        "voltage": 75,
        "frequency": 1000,
    })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rm.to_json(), f, indent=2)


EXECUTOR_LISTENER_ACTOR_NAME = "pluggable_protocol_tree_executor_listener"


def _subscribe_executor_listener(session: ProtocolSession) -> None:
    """Subscribe the executor_listener actor to the voltage/frequency ack
    topics so that acks deposited by the demo responder reach the
    active step's mailbox.

    _setup_demo_hardware wires ELECTRODES_STATE_APPLIED for the
    electrode handshake but knows nothing about the dropbot_protocol_controls
    columns — we must add the voltage/frequency acks ourselves.
    """
    if session._router is None:
        return
    for topic in (VOLTAGE_APPLIED, FREQUENCY_APPLIED):
        try:
            session._router.message_router_data.remove_subscriber_from_topic(
                topic=topic,
                subscribing_actor_name=EXECUTOR_LISTENER_ACTOR_NAME,
            )
        except Exception:
            pass
        session._router.message_router_data.add_subscriber_to_topic(
            topic=topic,
            subscribing_actor_name=EXECUTOR_LISTENER_ACTOR_NAME,
        )


def _subscribe_spy(session: ProtocolSession) -> None:
    """Watch all voltage/frequency request + ack topics."""
    if session._router is None:
        return
    for topic in (PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY,
                  VOLTAGE_APPLIED, FREQUENCY_APPLIED):
        try:
            session._router.message_router_data.remove_subscriber_from_topic(
                topic=topic, subscribing_actor_name=SPY_ACTOR_NAME,
            )
        except Exception:
            pass
        session._router.message_router_data.add_subscriber_to_topic(
            topic=topic, subscribing_actor_name=SPY_ACTOR_NAME,
        )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    path = Path(tempfile.gettempdir()) / "ppt4_vf_demo_protocol.json"
    _build_sample_protocol_file(path)
    print(f"\nWrote sample protocol to: {path}\n")

    with ProtocolSession.from_file(str(path),
                                   with_demo_hardware=True) as session:
        n_steps = len(session.manager.root.children)
        print(f"Loaded {n_steps} top-level steps "
              f"({len(session.manager.columns)} columns resolved).")

        subscribe_demo_responder(session._router)
        _subscribe_executor_listener(session)
        _subscribe_spy(session)

        print("\nStarting protocol...\n")
        session.start()

        if not session.wait(timeout=30.0):
            print("Protocol still running after 30s, stopping...")
            session.stop()
            session.wait(timeout=5.0)

    print("\nDone -- ProtocolSession context exited cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
