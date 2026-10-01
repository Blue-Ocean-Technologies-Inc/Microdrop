# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A device viewer layer adding or removing an alpha row must not trip the
interaction service's alpha observer: the change event's object is then the
alpha_map list itself, not an AlphaValue (#650 PR 0 review)."""

# Standard library imports.
from types import SimpleNamespace
from unittest.mock import MagicMock

# Microdrop package imports.
from device_viewer.default_settings import electrode_outline_key
from device_viewer.models.alpha import AlphaValue
from device_viewer.services.electrode_interaction_service import (
    ElectrodeInteractionControllerService,
)


def _stub_service():
    return SimpleNamespace(
        electrode_view_layer=MagicMock(),
        model=MagicMock(),
        electrode_state_recolor=MagicMock(),
        electrode_channel_change=MagicMock(),
    )


def test_row_added_or_removed_is_ignored():
    service = _stub_service()
    event = SimpleNamespace(object=[AlphaValue(key=electrode_outline_key)])

    ElectrodeInteractionControllerService._alpha_change(service, event)

    service.electrode_view_layer.redraw_electrode_lines.assert_not_called()


def test_value_change_still_redraws():
    service = _stub_service()
    event = SimpleNamespace(object=AlphaValue(key=electrode_outline_key))

    ElectrodeInteractionControllerService._alpha_change(service, event)

    service.electrode_view_layer.redraw_electrode_lines.assert_called_once()
