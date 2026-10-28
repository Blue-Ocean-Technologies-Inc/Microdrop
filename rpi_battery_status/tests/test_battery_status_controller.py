# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Polling the status file into the model with a fake clock, no timer."""

# Standard library imports.
import json

# Microdrop package imports.
from rpi_battery_status.consts import (
    LEVEL_LOW,
    LEVEL_UNAVAILABLE,
    STALE_AFTER_S,
)
from rpi_battery_status.controllers.battery_status_controller import (
    BatteryStatusController,
)

WRITTEN_AT = 1_800_000_000.0


def write_status(path, **fields):
    """Write a schema-1 snapshot stamped WRITTEN_AT to ``path``."""
    snapshot = {"schema": 1, "timestamp": WRITTEN_AT, **fields}
    path.write_text(json.dumps(snapshot))


def test_poll_applies_a_fresh_snapshot(tmp_path):
    path = tmp_path / "status.json"
    write_status(path, soc=30, voltage=23.0)
    controller = BatteryStatusController(path=path, clock=lambda: WRITTEN_AT + 1)

    controller.poll()

    assert controller.model.level == LEVEL_LOW
    assert controller.model.percent_text == "30 %"
    assert controller.model.voltage == 23.0


def test_poll_marks_a_stale_snapshot_unavailable(tmp_path):
    path = tmp_path / "status.json"
    write_status(path, soc=30)
    controller = BatteryStatusController(
        path=path, clock=lambda: WRITTEN_AT + STALE_AFTER_S + 1
    )

    controller.poll()

    assert controller.model.level == LEVEL_UNAVAILABLE


def test_poll_marks_a_vanished_file_unavailable(tmp_path):
    path = tmp_path / "status.json"
    write_status(path, soc=30)
    controller = BatteryStatusController(path=path, clock=lambda: WRITTEN_AT)
    controller.poll()

    assert controller.model.level == LEVEL_LOW

    path.unlink()
    controller.poll()

    assert controller.model.level == LEVEL_UNAVAILABLE


def test_poll_survives_a_malformed_file(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("not json")
    controller = BatteryStatusController(path=path, clock=lambda: WRITTEN_AT)

    controller.poll()

    assert controller.model.level == LEVEL_UNAVAILABLE


def test_poll_reads_the_real_pi_status_file(
    pi_charging_status_file, pi_charging_snapshot
):
    written_at = pi_charging_snapshot["timestamp"]
    controller = BatteryStatusController(
        path=pi_charging_status_file, clock=lambda: written_at + 2
    )

    controller.poll()

    assert controller.model.alive
    assert controller.model.glyph == "battery_charging_30"
    assert controller.model.time_to_full == 39768
