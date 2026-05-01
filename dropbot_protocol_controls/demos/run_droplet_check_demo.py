"""PPT-8 demo — droplet-check column with switchable in-process responder.

Opens a Qt window with the protocol tree on the left and a 5x5 device
viewer on the right. The 'Check Droplets' column is hidden by default —
header right-click to surface it.

The demo's responder defaults to 'drop_one' mode so the failure dialog
fires on the first run without any menu interaction. Use the Tools menu
to switch mode and Tools -> Re-run to iterate.

Run: pixi run python -m dropbot_protocol_controls.demos.run_droplet_check_demo
"""

import json
import logging

import dramatiq
from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QActionGroup, QAction

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.electrodes_column import make_electrodes_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from dropbot_controller.consts import DROPLETS_DETECTED
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.demos.base_demo_window import (
    BasePluggableProtocolDemoWindow, DemoConfig,
)
from pluggable_protocol_tree.demos.simple_device_viewer import (
    GRID_H, GRID_W, SimpleDeviceViewer,
)

from dropbot_protocol_controls.consts import (
    DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
    DROPLET_CHECK_DECISION_REQUEST,
    DROPLET_CHECK_DECISION_RESPONSE,
)
from dropbot_protocol_controls.protocol_columns.droplet_check_column import (
    make_droplet_check_column,
)
from dropbot_protocol_controls.demos.droplet_detection_responder import (
    DropletDetectionResponder,
)
# Side-effect import: instantiates the module-level _dialog_actor_singleton,
# which registers the @dramatiq.actor for `droplet_check_decision_listener`.
# In production this happens via DropbotProtocolControlsPlugin's own
# side-effect import; demos run without the plugin lifecycle, so the
# import has to be wired here. Without this, the failure dialog's
# DECISION_REQUEST publishes get DLQ'd with ActorNotFound.
from dropbot_protocol_controls.services import (  # noqa: F401
    droplet_check_decision_dialog_actor as _ddialog_actor,
)


# Module-level so the Tools menu can flip its `mode` at runtime and the
# next protocol run picks up the change.
_responder = DropletDetectionResponder(mode="drop_one")


# Electrode IDs match SimpleDeviceViewer's grid convention (e00..e24).
# The droplet-check handler resolves these via electrode_to_channel
# below; the IDs themselves are what shows up on the 5x5 grid.
_ELECTRODE_TO_CHANNEL = {f"e{i:02d}": i for i in range(GRID_W * GRID_H)}


# Module-level overlay listener target. PPT-3's run_widget.py uses the
# same pattern: keep the Dramatiq actor at module scope (so reloads
# don't re-register), and let post_build_setup bind the live viewer
# instance into this dict.
_overlay_target = {"viewer": None}


@dramatiq.actor(actor_name="ppt8_droplet_demo_actuation_overlay_listener",
                queue_name="default")
def _overlay_listener(message: str, topic: str, timestamp: float = None):
    """Paints actuated cells green on the side-panel device viewer.

    Subscribes to ELECTRODES_STATE_CHANGE (published by RoutesHandler /
    ElectrodesHandler when phases advance). The viewer reference lives
    in _overlay_target so the actor stays at module scope."""
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
    """PPT-3 builtins + droplet check (sufficient for the demo).
    Voltage/frequency/force are NOT needed here — focus is on the new
    column's behavior, not on integration with other PPT-7 columns."""
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_droplet_check_column(),
    ]


def _pre_populate(rm):
    """3 steps from the spec walkthrough — electrode IDs use the e00..e24
    convention so they line up with SimpleDeviceViewer's 5x5 grid."""
    rm.protocol_metadata["electrode_to_channel"] = dict(_ELECTRODE_TO_CHANNEL)
    rm.add_step(values={
        "name": "S1", "duration_s": 0.3,
        "electrodes": ["e00", "e01"],
        "check_droplets": True,
    })
    rm.add_step(values={
        "name": "S2", "duration_s": 0.3,
        "electrodes": ["e02", "e03", "e04"],
        "check_droplets": True,
    })
    rm.add_step(values={
        "name": "S3", "duration_s": 0.3,
        "electrodes": ["e05"],
        "check_droplets": False,
    })


_EXECUTOR_LISTENER_ACTOR_NAME = "pluggable_protocol_tree_executor_listener"


def _routing_setup(router):
    _responder.subscribe(router)
    # Demo-environment wiring. Production uses MessageRouterPlugin +
    # ACTOR_TOPIC_DICT contributions for these; demos run without that
    # lifecycle so we add subscribers directly.
    sub = router.message_router_data.add_subscriber_to_topic
    # Executor listener: handler.wait_for() needs both droplets-detected
    # acks and dialog-decision responses.
    for topic in (DROPLETS_DETECTED, DROPLET_CHECK_DECISION_RESPONSE):
        sub(topic=topic, subscribing_actor_name=_EXECUTOR_LISTENER_ACTOR_NAME)
    # Dialog actor: receives requests, shows confirm dialog, publishes choice.
    sub(topic=DROPLET_CHECK_DECISION_REQUEST,
        subscribing_actor_name=DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME)
    # Actuation overlay (green cells on the device viewer).
    sub(topic=ELECTRODES_STATE_CHANGE,
        subscribing_actor_name="ppt8_droplet_demo_actuation_overlay_listener")


def _make_side_panel(rm):
    return SimpleDeviceViewer(rm)


def _install_tools_menu(window):
    menu_bar = window.menuBar()
    tools_menu = menu_bar.addMenu("Tools")

    mode_menu = tools_menu.addMenu("Responder Mode")
    mode_group = QActionGroup(window)
    mode_group.setExclusive(True)
    for mode_label, mode_value in [
        ("Always succeed",      "succeed"),
        ("Drop one channel",    "drop_one"),
        ("Drop all channels",   "drop_all"),
        ("Error reply",         "error"),
    ]:
        action = QAction(mode_label, window)
        action.setCheckable(True)
        action.setChecked(mode_value == _responder.mode)
        action.triggered.connect(
            lambda _checked=False, mv=mode_value: _set_mode(mv)
        )
        mode_group.addAction(action)
        mode_menu.addAction(action)

    rerun = QAction("Re-run Protocol", window)
    rerun.setShortcut("Ctrl+R")
    rerun.triggered.connect(lambda: _rerun_protocol(window))
    tools_menu.addAction(rerun)


def _set_mode(mode_value):
    _responder.mode = mode_value
    logging.getLogger(__name__).info(
        "[droplet-check-demo] responder mode -> %s", mode_value,
    )


def _rerun_protocol(window):
    """Tell the demo's executor to start over from step 0."""
    window.executor.start()


def _post_build(window):
    _install_tools_menu(window)
    # Bind the side-panel viewer so the overlay actor can find it, and
    # follow the tree's selection + the executor's currently-running step
    # (PPT-3's run_widget.py wiring).
    device_view = window._side_panel
    if device_view is not None:
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
    title="PPT-8 Demo — Droplet Check Column (switchable responder)",
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
