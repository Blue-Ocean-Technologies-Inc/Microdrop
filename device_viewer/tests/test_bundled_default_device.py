# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The default device loads straight from the bundled file, and bundled
devices are read-only to saves (#89)."""

# Standard library imports.
import sys
from pathlib import Path

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences

# Microdrop package imports.
from device_viewer.consts import MASTER_SVG_FILE
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.preferences import DeviceViewerPreferences
from device_viewer.services.svg_persistence_service import (
    SvgPersistenceService,
    is_bundled_device,
)


@pytest.fixture
def preferences(tmp_path):
    return DeviceViewerPreferences(
        preferences=Preferences(), DEVICE_REPO_DIR=str(tmp_path)
    )


@pytest.fixture
def service(preferences):
    model = DeviceViewMainModel(preferences=preferences)

    return SvgPersistenceService(model=model, preferences=preferences)


def test_default_is_the_bundled_file_and_reading_writes_nothing(preferences, tmp_path):
    assert preferences.DEFAULT_SVG_FILE == str(MASTER_SVG_FILE)

    preferences.clone_traits(preferences.copyable_trait_names())

    assert list(tmp_path.iterdir()) == []


def test_save_refuses_a_bundled_device(service):
    service.load()

    assert service.bundled_device_loaded

    with pytest.raises(PermissionError):
        service.save()


def test_save_as_refuses_the_bundled_folder(service):
    service.load()

    with pytest.raises(PermissionError):
        service.save_as(str(MASTER_SVG_FILE.with_name("copy")))

    assert not MASTER_SVG_FILE.with_name("copy.svg").exists()


def test_save_as_from_a_bundled_device_carries_on_with_the_copy(service, tmp_path):
    service.load()
    route_layers = list(service.model.routes.layers)

    written_path = service.save_as(str(tmp_path / "copy"))

    assert written_path == str(tmp_path / "copy.svg")
    assert service.loaded_path == written_path
    assert service.model.electrodes.svg_model.filename == written_path
    assert not service.bundled_device_loaded
    assert not service.modified
    assert list(service.model.routes.layers) == route_layers

    electrode = next(iter(service.model.electrodes.electrodes.values()))
    electrode.channel = electrode.channel + 100
    service.save()

    assert f'data-channels="{electrode.channel}"' in Path(written_path).read_text()


def test_save_as_from_another_device_stays_on_it(service, tmp_path):
    service.load()
    original = service.save_as(str(tmp_path / "original"))

    service.save_as(str(tmp_path / "copy"))

    assert service.loaded_path == original
    assert (tmp_path / "copy.svg").exists()


def test_preferences_revert_leaves_the_default_device_alone(preferences):
    # Mirrors the preferences dialog: Revert resets the preference traits of
    # the pane's clone except those tagged no_revert.
    clone = preferences.clone_traits(
        [name for name in preferences.copyable_trait_names() if name != "preferences"]
    )

    assert clone._is_preference_trait("DEFAULT_SVG_FILE")
    assert clone.trait("DEFAULT_SVG_FILE").no_revert


@pytest.mark.skipif(sys.platform != "win32", reason="Windows path spelling")
def test_bundled_check_ignores_case_and_separators():
    respelled = str(MASTER_SVG_FILE).upper().replace("\\", "/")

    assert is_bundled_device(respelled)
