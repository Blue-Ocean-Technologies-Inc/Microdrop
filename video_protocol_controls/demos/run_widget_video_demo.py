"""PPT-6 demo — protocol tree with the Video/Record/Capture columns.

Run: pixi run python -m video_protocol_controls.demos.run_widget_video_demo
"""

import json
import logging

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.demos.base_demo_window import (
    BasePluggableProtocolDemoWindow, DemoConfig, StatusReadout,
)

from device_viewer.consts import (
    DEVICE_VIEWER_CAMERA_ACTIVE,
    DEVICE_VIEWER_SCREEN_CAPTURE,
    DEVICE_VIEWER_SCREEN_RECORDING,
)

from video_protocol_controls.demos.camera_responder import (
    subscribe_demo_responder,
)
from video_protocol_controls.protocol_columns import (
    make_video_column, make_record_column, make_capture_column,
)


def _fmt_camera(message: str) -> str:
    """Render the published 'true'/'false' camera state as 'on'/'off'."""
    return "on" if message.strip().lower() == "true" else "off"


def _fmt_capture(message: str) -> str:
    """Render the captured step_id from the JSON payload."""
    try:
        payload = json.loads(message)
    except (TypeError, ValueError):
        return "—"
    return payload.get("step_id", "—")


def _fmt_record(message: str) -> str:
    """Render the recording action ('start' or 'stop') as 'active'/'stopped'."""
    try:
        payload = json.loads(message)
    except (TypeError, ValueError):
        return "—"
    return "active" if payload.get("action") == "start" else "stopped"


def _columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
        make_video_column(), make_record_column(), make_capture_column(),
    ]


def _pre_populate(rm):
    """3 steps exercising the three flag combinations called out in the plan."""
    rm.add_step(values={
        "name": "Step 1: video on, capture/record off",
        "duration_s": 0.3,
        "video": True, "capture": False, "record": False,
    })
    rm.add_step(values={
        "name": "Step 2: video on, capture + record on",
        "duration_s": 0.3,
        "video": True, "capture": True, "record": True,
    })
    rm.add_step(values={
        "name": "Step 3: all off (cleanup expected)",
        "duration_s": 0.3,
        "video": False, "capture": False, "record": False,
    })


config = DemoConfig(
    columns_factory=_columns,
    title="PPT-6 Demo — Video / Capture / Record",
    pre_populate=_pre_populate,
    routing_setup=lambda router: subscribe_demo_responder(router),
    # No phase ack — video columns are fire-and-forget. The base will
    # show only the per-step elapsed timer (no per-phase timer).
    phase_ack_topic=None,
    status_readouts=[
        StatusReadout("Camera",  DEVICE_VIEWER_CAMERA_ACTIVE,    _fmt_camera,  initial="off"),
        StatusReadout("Capture", DEVICE_VIEWER_SCREEN_CAPTURE,   _fmt_capture, initial="—"),
        StatusReadout("Record",  DEVICE_VIEWER_SCREEN_RECORDING, _fmt_record,  initial="stopped"),
    ],
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
