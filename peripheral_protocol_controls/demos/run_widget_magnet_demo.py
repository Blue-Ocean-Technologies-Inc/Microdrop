"""PPT-5 demo — protocol tree with the magnet compound column.

Run: pixi run python -m peripheral_protocol_controls.demos.run_widget_magnet_demo
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
from pluggable_protocol_tree.models._compound_adapters import _expand_compound

from peripheral_controller.consts import (
    MAGNET_APPLIED, MIN_ZSTAGE_HEIGHT_MM, PROTOCOL_SET_MAGNET,
)
from peripheral_controller.preferences import PeripheralPreferences
from peripheral_protocol_controls.demos.magnet_responder import (
    subscribe_demo_responder,
)
from peripheral_protocol_controls.protocol_columns.magnet_column import (
    make_magnet_column,
)


def _fmt_magnet_height(message: str) -> str:
    """Render the actual physical zstage height the production
    zstage_state_setter_service would move to for this request:
      - retract  → PeripheralPreferences().down_height_mm
      - engage at sentinel (height < MIN_ZSTAGE_HEIGHT_MM)
                 → PeripheralPreferences().up_height_mm  (live pref)
      - engage at explicit height → that height

    Reads height from the PROTOCOL_SET_MAGNET request payload — the
    MAGNET_APPLIED ack itself is just '0'/'1' on the wire (production
    wire format pinned by test_protocol_set_magnet)."""
    try:
        payload = json.loads(message)
    except (TypeError, ValueError):
        return "—"
    prefs = PeripheralPreferences()
    if not payload.get("on"):
        return f"{prefs.down_height_mm:.1f} mm"
    height = payload.get("height_mm", 0.0)
    if height < MIN_ZSTAGE_HEIGHT_MM:
        return f"{prefs.up_height_mm:.1f} mm"
    return f"{height:.1f} mm"


def _columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
        *_expand_compound(make_magnet_column()),
    ]


def _pre_populate(rm):
    rm.add_step(values={
        "name": "Step 1: engage at Default (sentinel; uses live pref)",
        "duration_s": 0.2,
        "magnet_on": True, "magnet_height_mm": 0.0,
    })
    rm.add_step(values={
        "name": "Step 2: engage at 12.0 mm explicit",
        "duration_s": 0.2,
        "magnet_on": True, "magnet_height_mm": 12.0,
    })
    rm.add_step(values={
        "name": "Step 3: retract",
        "duration_s": 0.2,
        "magnet_on": False, "magnet_height_mm": 0.0,
    })


config = DemoConfig(
    columns_factory=_columns,
    title="PPT-5 Demo — Magnet",
    pre_populate=_pre_populate,
    routing_setup=lambda router: subscribe_demo_responder(router),
    phase_ack_topic=MAGNET_APPLIED,
    status_readouts=[
        StatusReadout("Magnet", MAGNET_APPLIED,
                      lambda m: "engaged" if m == "1" else "retracted"),
        StatusReadout("Magnet Height", PROTOCOL_SET_MAGNET, _fmt_magnet_height),
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
