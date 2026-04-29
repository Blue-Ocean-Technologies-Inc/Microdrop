"""PPT-7 demo - protocol tree with the Force column reacting to a
published CALIBRATION_DATA message.

Opens a Qt window with 3 pre-populated steps (voltages 75/100/120 V).
500 ms after the window appears, a fake CALIBRATION_DATA payload is
published; this propagates calibration_data_listener -> CalibrationCache
-> cache_changed -> Qt model dataChanged, and all 3 Force cells
transition from blank to numeric values.

Run: pixi run python -m dropbot_protocol_controls.demos.run_force_demo
"""

import json
import logging

from pyface.qt.QtCore import QTimer

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.electrodes_column import make_electrodes_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
from pluggable_protocol_tree.demos.base_demo_window import (
    BasePluggableProtocolDemoWindow, DemoConfig,
)

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from device_viewer.consts import CALIBRATION_DATA

from dropbot_protocol_controls.consts import CALIBRATION_LISTENER_ACTOR_NAME
from dropbot_protocol_controls.protocol_columns.force_column import (
    make_force_column,
)
from dropbot_protocol_controls.protocol_columns.frequency_column import (
    make_frequency_column,
)
from dropbot_protocol_controls.protocol_columns.voltage_column import (
    make_voltage_column,
)


# Publish 500 ms after the window appears - long enough that the user
# can see the cells start blank, short enough not to feel like a delay.
_CALIBRATION_PUBLISH_DELAY_MS = 500

# Plausible mid-range calibration: 2.0 pF/mm^2 liquid, 0.5 pF/mm^2
# filler -> C/A = 1.5 pF/mm^2. With voltages 75/100/120 V this yields
# Force values around 4.2 / 7.5 / 10.8 mN/m (visible as 3 distinct,
# non-blank cells).
_DEMO_CALIBRATION_PAYLOAD = json.dumps({
    "liquid_capacitance_over_area": 2.0,
    "filler_capacitance_over_area": 0.5,
})


def subscribe_calibration_listener(router) -> None:
    """Subscribe the calibration_data_listener actor to CALIBRATION_DATA
    on a bare router. Mirrors voltage_frequency_responder.subscribe_demo_responder
    - demos run without MessageRouterPlugin, so the subscription that
    plugin.start() would normally install has to be wired by hand here."""
    router.message_router_data.add_subscriber_to_topic(
        topic=CALIBRATION_DATA,
        subscribing_actor_name=CALIBRATION_LISTENER_ACTOR_NAME,
    )


def _columns():
    """PPT-3 builtins + voltage + frequency + force."""
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_voltage_column(), make_frequency_column(),
        make_force_column(),
    ]


def _pre_populate(rm):
    """3 steps with the voltages called out in the Task 10 spec."""
    rm.add_step(values={
        "name": "S1",
        "duration_s": 0.3,
        "voltage": 75,
        "frequency": 10000,
    })
    rm.add_step(values={
        "name": "S2",
        "duration_s": 0.3,
        "voltage": 100,
        "frequency": 10000,
    })
    rm.add_step(values={
        "name": "S3",
        "duration_s": 0.3,
        "voltage": 120,
        "frequency": 10000,
    })


def _routing_setup(router):
    """Wire the calibration listener so the published CALIBRATION_DATA
    message reaches the actor that updates the cache."""
    subscribe_calibration_listener(router)


def _publish_demo_calibration():
    """Fired by QTimer.singleShot 500 ms after the window opens. The
    publish should propagate _on_calibration -> cache.cache_changed ->
    MvcTreeModel.dataChanged for the Force column -> repaint of all 3
    cells from blank to a formatted force value."""
    logging.getLogger(__name__).info(
        "[force-demo] publishing CALIBRATION_DATA: %s",
        _DEMO_CALIBRATION_PAYLOAD,
    )
    publish_message(message=_DEMO_CALIBRATION_PAYLOAD, topic=CALIBRATION_DATA)


def _post_build(window):
    """Schedule the one-shot calibration publish after the window is
    constructed. QTimer.singleShot defers to the GUI event loop, so the
    publish only runs after .show() has actually painted the cells."""
    QTimer.singleShot(_CALIBRATION_PUBLISH_DELAY_MS, _publish_demo_calibration)


config = DemoConfig(
    columns_factory=_columns,
    title="PPT-7 Demo - Force Column (auto calibration publish)",
    pre_populate=_pre_populate,
    routing_setup=_routing_setup,
    # Standard PPT-3 phase-ack topic; the base wires the electrode
    # responder + ELECTRODES_STATE_APPLIED listener for us.
    phase_ack_topic=ELECTRODES_STATE_APPLIED,
    post_build_setup=_post_build,
)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    BasePluggableProtocolDemoWindow.run(config)


if __name__ == "__main__":
    from microdrop_utils.broker_server_helpers import (
        redis_server_context, dramatiq_workers_context,
    )
    with redis_server_context():
        with dramatiq_workers_context():
            main()
