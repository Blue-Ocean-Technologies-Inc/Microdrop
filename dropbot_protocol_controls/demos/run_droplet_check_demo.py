"""PPT-8 demo — droplet-check column with switchable in-process responder.

Opens a Qt window with 3 pre-populated steps. The 'Check Droplets' column
is hidden by default — header right-click to surface it.

The demo's responder defaults to 'drop_one' mode so the failure dialog
fires on the first run without any menu interaction. Use the Tools menu
to switch mode and Tools -> Re-run to iterate.

Run: pixi run python -m dropbot_protocol_controls.demos.run_droplet_check_demo
"""

import logging

from pyface.qt.QtGui import QActionGroup, QAction

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

from dropbot_protocol_controls.protocol_columns.droplet_check_column import (
    make_droplet_check_column,
)
from dropbot_protocol_controls.demos.droplet_detection_responder import (
    DropletDetectionResponder,
)


# Module-level so the Tools menu can flip its `mode` at runtime and the
# next protocol run picks up the change.
_responder = DropletDetectionResponder(mode="drop_one")


# Map electrode IDs to channels (1-indexed, deterministic).
_ELECTRODE_TO_CHANNEL = {f"e{i}": i for i in range(1, 7)}


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
    """3 steps from the spec walkthrough."""
    rm.protocol_metadata["electrode_to_channel"] = dict(_ELECTRODE_TO_CHANNEL)
    rm.add_step(values={
        "name": "S1", "duration_s": 0.3,
        "activated_electrodes": ["e1", "e2"],
        "check_droplets": True,
    })
    rm.add_step(values={
        "name": "S2", "duration_s": 0.3,
        "activated_electrodes": ["e3", "e4", "e5"],
        "check_droplets": True,
    })
    rm.add_step(values={
        "name": "S3", "duration_s": 0.3,
        "activated_electrodes": ["e6"],
        "check_droplets": False,
    })


def _routing_setup(router):
    _responder.subscribe(router)


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


config = DemoConfig(
    columns_factory=_columns,
    title="PPT-8 Demo — Droplet Check Column (switchable responder)",
    pre_populate=_pre_populate,
    routing_setup=_routing_setup,
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
