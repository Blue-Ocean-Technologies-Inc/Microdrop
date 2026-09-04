# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Path handling in the legacy import scanner and dialog model.

Built from scratch under tmp_path, so unlike test_legacy_protocol_import
these never skip for want of a sample corpus. They pin the behaviour the
pathlib conversion (#574) had to preserve -- in particular that a stored
path containing ``..`` still matches its scanned dropdown entry."""

# Third-party imports.
import pytest

# Microdrop package imports.
from pluggable_protocol_tree.services.legacy_protocol_import import (
    legacy_device_display_name,
    scan_for_device_folders,
)
from pluggable_protocol_tree.services.legacy_protocol_import.consts import (
    DEVICE_SVG_FILENAME,
    DEVICES_DIR_NAME,
    NO_SELECTION_INDEX,
)
from pluggable_protocol_tree.views.legacy_import_dialog import (
    LegacyImportDialogModel,
)


def _device_folder(parent, name):
    """A minimal Device Folder: a directory holding a device.svg."""
    folder = parent / name
    folder.mkdir(parents=True)
    (folder / DEVICE_SVG_FILENAME).write_text("<svg/>", encoding="utf-8")
    return folder


# --------------------------------------------------------------------------
# legacy_device_display_name
# --------------------------------------------------------------------------


def test_display_name_of_device_svg_is_its_folder(tmp_path):
    folder = _device_folder(tmp_path, "Zika")

    assert legacy_device_display_name(str(folder / DEVICE_SVG_FILENAME)) == "Zika"


def test_display_name_of_a_hand_picked_svg_is_its_stem(tmp_path):
    assert legacy_device_display_name(str(tmp_path / "MyChip.svg")) == "MyChip"


def test_display_name_looks_through_a_parent_segment(tmp_path):
    dotted = tmp_path / "Other" / ".." / "Zika" / DEVICE_SVG_FILENAME

    assert legacy_device_display_name(str(dotted)) == "Zika"


# --------------------------------------------------------------------------
# scan_for_device_folders -- the three accepted directory shapes
# --------------------------------------------------------------------------


def test_scan_accepts_a_microdrop_root(tmp_path):
    devices = tmp_path / DEVICES_DIR_NAME
    _device_folder(devices, "Zika")
    _device_folder(devices, "Ebola")

    found = scan_for_device_folders(str(tmp_path))

    assert [device.name for device in found] == ["Ebola", "Zika"]
    assert found[0].device_svg_path == str(devices / "Ebola" / DEVICE_SVG_FILENAME)


def test_scan_accepts_a_single_device_folder(tmp_path):
    folder = _device_folder(tmp_path, "Zika")

    found = scan_for_device_folders(str(folder))

    assert [device.name for device in found] == ["Zika"]


def test_scan_accepts_a_plain_parent_of_device_folders(tmp_path):
    _device_folder(tmp_path, "Zika")
    (tmp_path / "not-a-device").mkdir()

    found = scan_for_device_folders(str(tmp_path))

    assert [device.name for device in found] == ["Zika"]


@pytest.mark.parametrize("root", ["", "  ", "no/such/directory"])
def test_scan_returns_empty_rather_than_raising(root):
    assert scan_for_device_folders(root) == []


def test_scan_returns_empty_for_a_file(tmp_path):
    a_file = tmp_path / "device.svg"
    a_file.write_text("<svg/>", encoding="utf-8")

    assert scan_for_device_folders(str(a_file)) == []


# --------------------------------------------------------------------------
# LegacyImportDialogModel.restore_selection
# --------------------------------------------------------------------------


def test_restore_selection_matches_the_scanned_entry(tmp_path):
    folder = _device_folder(tmp_path, "Zika")
    model = LegacyImportDialogModel(root_path=str(tmp_path))

    model.restore_selection(str(folder / DEVICE_SVG_FILENAME), "")

    assert model.selected_device_index == 0
    assert model.device_svg_path == str(folder / DEVICE_SVG_FILENAME)


def test_restore_selection_matches_through_a_parent_segment(tmp_path):
    """A path the user typed into the editable field is persisted verbatim,
    so a stored ``.../Other/../Zika/device.svg`` must still resolve onto the
    scanned Zika entry rather than falling through as an override."""
    folder = _device_folder(tmp_path, "Zika")
    _device_folder(tmp_path, "Other")
    dotted = tmp_path / "Other" / ".." / "Zika" / DEVICE_SVG_FILENAME

    model = LegacyImportDialogModel(root_path=str(tmp_path))
    model.restore_selection(str(dotted), "")

    assert [device.name for device in model.device_folders] == ["Other", "Zika"]
    assert model.selected_device_index == 1
    assert model.device_svg_path == str(folder / DEVICE_SVG_FILENAME)


def test_restore_selection_ignores_a_path_that_no_longer_exists(tmp_path):
    _device_folder(tmp_path, "Zika")
    model = LegacyImportDialogModel(root_path=str(tmp_path))

    model.restore_selection(str(tmp_path / "Gone" / DEVICE_SVG_FILENAME), "")

    assert model.selected_device_index == 0


def test_restore_selection_keeps_an_unscanned_path_as_an_override(tmp_path):
    _device_folder(tmp_path, "Zika")
    elsewhere = tmp_path / "elsewhere.svg"
    elsewhere.write_text("<svg/>", encoding="utf-8")

    model = LegacyImportDialogModel(root_path=str(tmp_path))
    model.restore_selection(str(elsewhere), "")

    assert model.device_svg_path == str(elsewhere)


def test_empty_root_selects_nothing(tmp_path):
    model = LegacyImportDialogModel(root_path=str(tmp_path))

    assert model.device_folders == []
    assert model.selected_device_index == NO_SELECTION_INDEX
    assert model.device_svg_path == ""
