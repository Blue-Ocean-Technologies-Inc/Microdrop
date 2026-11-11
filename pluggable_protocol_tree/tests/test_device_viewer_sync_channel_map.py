# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The live device channel map survives protocol_metadata replacement."""

# Third-party imports.
import pytest

# Microdrop package imports.
from pluggable_protocol_tree.consts import ELECTRODE_TO_CHANNEL_KEY
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services import device_viewer_sync
from pluggable_protocol_tree.services.device_viewer_sync import (
    DeviceViewerSyncController,
)

LIVE_MAP = {"electrode000": 0, "electrode001": 1}
STALE_MAP = {"electrode000": 40, "electrode001": 41}


@pytest.fixture
def sync(monkeypatch):
    """A sync controller without its dramatiq actor (registered once per
    process in the app; the metadata observers do not need it)."""
    monkeypatch.setattr(
        device_viewer_sync,
        "generate_class_method_dramatiq_listener_actor",
        lambda **kwargs: None,
    )

    return DeviceViewerSyncController(row_manager=RowManager(columns=[]))


def test_new_protocol_keeps_the_live_device_map(sync):
    sync.electrode_ids_channels_map = LIVE_MAP

    sync.row_manager.protocol_metadata = {}

    assert sync.row_manager.protocol_metadata[ELECTRODE_TO_CHANNEL_KEY] == LIVE_MAP


def test_loaded_stale_map_is_replaced_by_the_live_device_map(sync):
    sync.electrode_ids_channels_map = LIVE_MAP

    sync.row_manager.protocol_metadata = {
        ELECTRODE_TO_CHANNEL_KEY: STALE_MAP,
        "other": "kept",
    }

    metadata = sync.row_manager.protocol_metadata
    assert metadata[ELECTRODE_TO_CHANNEL_KEY] == LIVE_MAP
    assert metadata["other"] == "kept"


def test_loaded_map_is_kept_before_any_device_publishes(sync):
    sync.row_manager.protocol_metadata = {ELECTRODE_TO_CHANNEL_KEY: STALE_MAP}

    assert sync.row_manager.protocol_metadata[ELECTRODE_TO_CHANNEL_KEY] == STALE_MAP
