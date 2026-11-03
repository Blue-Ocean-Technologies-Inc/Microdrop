# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The magnet engage replies on the Portable DropBot Settings tab: each
MAGNET_ENGAGE_UPDATED outcome lands on the status line, and a read fills
the pane's unapplied copy of the field, never the preferences node."""

# Microdrop package imports.
from portable_dropbot_controller.consts import MagnetEngageUpdated
from portable_dropbot_status_and_controls.consts import DEFAULT_MAGNET_ENGAGE_MM
from portable_dropbot_status_and_controls.models.magnet_engage_model import (
    MagnetEngageModel,
)
from portable_dropbot_status_and_controls.preferences import (
    PortableDropbotSettingsPreferences,
    PortableDropbotSettingsPreferencesPane,
)


def test_read_shows_the_board_height():
    model = MagnetEngageModel()

    model.apply_update(MagnetEngageUpdated(action="read", engage_mm=12.5))

    assert model.status == "Board: 12.500 mm"


def test_write_preset_and_error_outcomes_reach_the_status_line():
    model = MagnetEngageModel()

    model.apply_update(MagnetEngageUpdated(action="write", engage_mm=14.0))
    assert model.status.startswith("Written to RAM: 14.000 mm")

    model.apply_update(MagnetEngageUpdated(action="preset"))
    assert model.status.startswith("Preset to flash")

    model.apply_update(MagnetEngageUpdated(action="read", error="read failed"))
    assert model.status == "Read failed: read failed"


def test_read_fills_the_panes_unapplied_copy_not_the_node():
    pane = PortableDropbotSettingsPreferencesPane(
        model=PortableDropbotSettingsPreferences()
    )
    pane.trait_context()

    pane.magnet_engage.apply_update(MagnetEngageUpdated(action="read", engage_mm=12.5))

    assert pane._model.magnet_engage_mm == 12.5
    assert pane.model.magnet_engage_mm == DEFAULT_MAGNET_ENGAGE_MM
