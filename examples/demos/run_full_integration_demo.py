"""Full-stack integration demo: PPT-3 electrodes/routes + PPT-4 voltage/
frequency + PPT-5 magnet, all in one window. Verifies priority bucketing
in practice (priority 20 V/F/magnet bucket completes before priority 30
RoutesHandler publishes electrodes).

Run: pixi run python -m examples.demos.run_full_integration_demo
"""

import json
import logging

import dramatiq
from pyface.qt.QtCore import Qt

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.electrodes_column import make_electrodes_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.linear_repeats_column import (
    make_linear_repeats_column,
)
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repeat_duration_column import (
    make_repeat_duration_column,
)
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.soft_end_column import make_soft_end_column
from pluggable_protocol_tree.builtins.soft_start_column import make_soft_start_column
from pluggable_protocol_tree.builtins.trail_length_column import make_trail_length_column
from pluggable_protocol_tree.builtins.trail_overlay_column import (
    make_trail_overlay_column,
)
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.demos.base_demo_window import (
    BasePluggableProtocolDemoWindow, DemoConfig, StatusReadout,
)
from pluggable_protocol_tree.demos.simple_device_viewer import (
    GRID_H, GRID_W, SimpleDeviceViewer,
)
from pluggable_protocol_tree.models._compound_adapters import _expand_compound

from dropbot_controller.consts import VOLTAGE_APPLIED, FREQUENCY_APPLIED
from dropbot_protocol_controls.demos.voltage_frequency_responder import (
    subscribe_demo_responder as subscribe_vf_responder,
)
from dropbot_protocol_controls.protocol_columns.frequency_column import (
    make_frequency_column,
)
from dropbot_protocol_controls.protocol_columns.voltage_column import (
    make_voltage_column,
)

from peripheral_controller.consts import MAGNET_APPLIED
from peripheral_protocol_controls.demos.magnet_responder import (
    subscribe_demo_responder as subscribe_magnet_responder,
)
from peripheral_protocol_controls.protocol_columns.magnet_column import (
    make_magnet_column,
)


# Module-level overlay listener — captures the device viewer via a
# global hook set by the post_build_setup callback. The actor name uses
# the integration demo's own slot in _DEMO_PREFIXES (ppt12_demo_*) so the
# stale-subscriber purger handles it correctly.
_overlay_target = {"viewer": None}


@dramatiq.actor(actor_name="ppt12_demo_integration_overlay_listener",
                queue_name="default")
def _overlay_listener(message: str, topic: str, timestamp: float = None):
    viewer = _overlay_target["viewer"]
    if viewer is None:
        return
    try:
        payload = json.loads(message)
    except (TypeError, ValueError):
        return
    electrodes = payload.get("electrodes", []) or []
    viewer.actuation_changed.emit(list(electrodes))


def _columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_trail_length_column(), make_trail_overlay_column(),
        make_soft_start_column(), make_soft_end_column(),
        make_repeat_duration_column(), make_linear_repeats_column(),
        # PPT-4
        make_voltage_column(), make_frequency_column(),
        # PPT-5 (compound, expanded)
        *_expand_compound(make_magnet_column()),
    ]


def _pre_populate(rm):
    rm.protocol_metadata["electrode_to_channel"] = {
        f"e{i:02d}": i for i in range(GRID_W * GRID_H)
    }
    rm.add_step(values={
        "name": "Step 1: 100V/10kHz, magnet=Default, route top row",
        "duration_s": 0.3,
        "voltage": 100, "frequency": 10000,
        "magnet_on": True, "magnet_height_mm": 0.0,   # sentinel = Default
        "routes": [["e00", "e01", "e02", "e03", "e04"]],
        "trail_length": 1,
    })
    rm.add_step(values={
        "name": "Step 2: 120V/5kHz, magnet=12mm, diagonal",
        "duration_s": 0.3,
        "voltage": 120, "frequency": 5000,
        "magnet_on": True, "magnet_height_mm": 12.0,
        "routes": [["e00", "e06", "e12", "e18", "e24"]],
        "trail_length": 1,
    })
    rm.add_step(values={
        "name": "Step 3: 75V/1kHz cooldown, retract magnet",
        "duration_s": 0.3,
        "voltage": 75, "frequency": 1000,
        "magnet_on": False, "magnet_height_mm": 0.0,
    })


def _routing_setup(router):
    """All three demo responders + the integration overlay listener."""
    subscribe_vf_responder(router)
    subscribe_magnet_responder(router)
    router.message_router_data.add_subscriber_to_topic(
        topic=ELECTRODES_STATE_CHANGE,
        subscribing_actor_name="ppt12_demo_integration_overlay_listener",
    )


def _post_build(window):
    """Wire the side-panel: device viewer follows the tree's current
    selection AND the executor's currently-running step."""
    central = window.centralWidget()
    device_view = central.widget(1)
    _overlay_target["viewer"] = device_view

    sel_model = window.widget.tree.selectionModel()
    sel_model.currentRowChanged.connect(
        lambda cur, _prev: device_view.set_active_row(
            cur.data(Qt.UserRole) if cur.isValid() else None
        )
    )
    window.executor.qsignals.step_started.connect(device_view.set_active_row)


config = DemoConfig(
    columns_factory=_columns,
    title="Full Integration Demo — PPT-3 routes + PPT-4 V/F + PPT-5 magnet",
    window_size=(1300, 700),
    pre_populate=_pre_populate,
    routing_setup=_routing_setup,
    phase_ack_topic=ELECTRODES_STATE_APPLIED,
    status_readouts=[
        StatusReadout("Voltage",   VOLTAGE_APPLIED,   lambda m: f"{int(m)} V"),
        StatusReadout("Frequency", FREQUENCY_APPLIED, lambda m: f"{int(m)} Hz"),
        StatusReadout("Magnet",    MAGNET_APPLIED,
                      lambda m: "engaged" if m == "1" else "retracted"),
    ],
    side_panel_factory=lambda rm: SimpleDeviceViewer(rm),
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
