"""PPT-3 demo — protocol tree + electrodes/routes + device viewer +
PPT-2 ack-roundtrip column.

Run: pixi run python -m pluggable_protocol_tree.demos.run_widget
"""

import json
import logging

import dramatiq

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
from pluggable_protocol_tree.demos.ack_roundtrip_column import (
    DEMO_APPLIED_TOPIC, DEMO_REQUEST_TOPIC, RESPONDER_ACTOR_NAME,
    make_ack_roundtrip_column,
)
from pluggable_protocol_tree.demos.base_demo_window import (
    BasePluggableProtocolDemoWindow, DemoConfig,
)
from pluggable_protocol_tree.demos.message_column import make_message_column
from pluggable_protocol_tree.demos.simple_device_viewer import (
    GRID_H, GRID_W, SimpleDeviceViewer,
)
from pyface.qt.QtCore import Qt


# Module-level overlay listener — captures the device viewer via a
# global hook set by the post_build_setup callback. Keeping the actor
# at module level avoids duplicate-registration errors when the demo
# is reloaded in the same process.
_overlay_target = {"viewer": None}


@dramatiq.actor(actor_name="ppt_demo_actuation_overlay_listener",
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
        make_message_column(), make_ack_roundtrip_column(),
    ]


def _pre_populate(rm):
    """Seed the electrode→channel mapping. e00..e24 → channels 0..24."""
    rm.protocol_metadata["electrode_to_channel"] = {
        f"e{i:02d}": i for i in range(GRID_W * GRID_H)
    }


def _routing_setup(router):
    """PPT-2 ack-roundtrip column responder + actuation-overlay listener
    subscription. The overlay actor itself is registered at module import."""
    router.message_router_data.add_subscriber_to_topic(
        topic=DEMO_REQUEST_TOPIC,
        subscribing_actor_name=RESPONDER_ACTOR_NAME,
    )
    router.message_router_data.add_subscriber_to_topic(
        topic=DEMO_APPLIED_TOPIC,
        subscribing_actor_name="pluggable_protocol_tree_executor_listener",
    )
    router.message_router_data.add_subscriber_to_topic(
        topic=ELECTRODES_STATE_CHANGE,
        subscribing_actor_name="ppt_demo_actuation_overlay_listener",
    )


def _make_side_panel(rm):
    return SimpleDeviceViewer(rm)


def _post_build(window):
    """Wire the PPT-3-specific side-panel signals: device viewer follows
    the tree's current selection AND the executor's currently-running step.
    Also bind the module-level overlay listener target to this window's
    device viewer."""
    # Find the device viewer in the splitter (it's the right widget).
    central = window.centralWidget()
    # The base wraps tree + side panel in a QSplitter when side_panel_factory
    # is provided. The side panel is the second widget.
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
    title="Pluggable Protocol Tree — PPT-3 Demo",
    window_size=(1100, 650),
    pre_populate=_pre_populate,
    routing_setup=_routing_setup,
    phase_ack_topic=ELECTRODES_STATE_APPLIED,
    side_panel_factory=_make_side_panel,
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
