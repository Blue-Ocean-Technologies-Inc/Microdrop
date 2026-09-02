# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Zone types are app-global (#596): they mirror into preferences and must
survive undo and a fresh model construction."""

# Microdrop package imports.
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.preferences import DeviceViewerPreferences


def test_zone_types_mirror_into_preferences_and_survive_undo():
    preferences = DeviceViewerPreferences()
    model = DeviceViewMainModel(preferences=preferences)
    assert dict(preferences.zone_type_names) == {
        "heating": "heating",
        "mixing": "mixing",
    }
    model.zones.add_zone_type("cooling", "#123456")
    assert preferences.zone_type_colors["cooling"] == "#123456"
    model.zones.remove_zone_type("cooling")
    assert "cooling" not in preferences.zone_type_names
    model.zones.undo()
    assert preferences.zone_type_names["cooling"] == "cooling"
    restored = DeviceViewMainModel(preferences=preferences)
    assert [z.id for z in restored.zones.zone_types] == ["heating", "mixing", "cooling"]
