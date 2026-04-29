"""PPT-11 demo — synthetic enabled+count compound column.

Now uses the BasePluggableProtocolDemoWindow + gains Run/Pause/Stop +
status bar / step elapsed timer for free.

Run: pixi run python -m pluggable_protocol_tree.demos.run_widget_compound_demo
"""

import logging

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.demos.base_demo_window import (
    BasePluggableProtocolDemoWindow, DemoConfig,
)
from pluggable_protocol_tree.demos.enabled_count_compound import (
    make_enabled_count_compound,
)
from pluggable_protocol_tree.models._compound_adapters import _expand_compound


def _columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
        *_expand_compound(make_enabled_count_compound()),
    ]


def _pre_populate(rm):
    rm.add_step(values={
        "name": "Step 1: enabled, count=5",
        "duration_s": 0.2,
        "ec_enabled": True, "ec_count": 5,
    })
    rm.add_step(values={
        "name": "Step 2: disabled (count read-only)",
        "duration_s": 0.2,
        "ec_enabled": False, "ec_count": 0,
    })
    rm.add_step(values={
        "name": "Step 3: enabled, count=99",
        "duration_s": 0.2,
        "ec_enabled": True, "ec_count": 99,
    })


config = DemoConfig(
    columns_factory=_columns,
    title="PPT-11 Demo — Compound Column Framework",
    pre_populate=_pre_populate,
    phase_ack_topic=None,    # synthetic compound has no ack-emitting handlers
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
