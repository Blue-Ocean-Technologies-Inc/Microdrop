# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the Qt-free device SVG persistence service (#782)."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
import pytest

# Microdrop package imports.
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.preferences import DeviceViewerPreferences
from device_viewer.services.svg_persistence_service import SvgPersistenceService

BUNDLED_2X3 = (
    Path(__file__).resolve().parents[1] / "resources" / "devices" / "2x3device.svg"
)


@pytest.fixture
def service():
    model = DeviceViewMainModel(preferences=DeviceViewerPreferences())

    return SvgPersistenceService(model=model)


def test_round_trip_keeps_electrode_ids_and_channels(service, tmp_path):
    assert service.load(str(BUNDLED_2X3)) == 0
    assert service.loaded_path == str(BUNDLED_2X3)

    original = dict(service.model.electrodes.electrode_ids_channels_map)
    assert original

    # The suffix is added when the chosen name lacks it.
    service.save_as(str(tmp_path / "copy"))
    saved_file = tmp_path / "copy.svg"
    assert saved_file.exists()

    service.load(str(saved_file))

    assert service.loaded_path == str(saved_file)
    assert dict(service.model.electrodes.electrode_ids_channels_map) == original


def test_modified_flag_transitions(service, tmp_path):
    service.load(str(BUNDLED_2X3))
    service.save_as(str(tmp_path / "device.svg"))
    service.load(str(tmp_path / "device.svg"))

    assert not service.modified

    electrode = next(iter(service.model.electrodes.electrodes.values()))
    electrode.channel = electrode.channel + 100

    assert service.modified

    service.save()

    assert not service.modified

    service.model.electrodes.svg_model.area_scale = 2.0

    assert service.modified

    # Reloading discards the edit, so the fresh device is unmodified.
    service.load(str(tmp_path / "device.svg"))

    assert not service.modified
