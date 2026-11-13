# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""RecordingOverlayTimeline: the channels-at-time lookup and the overlay
sidecar round trip."""

# Standard library imports.
import json

# Microdrop package imports.
from device_viewer.consts import RECORDING_OVERLAY_SIDECAR_VERSION
from device_viewer.models.recording_overlay import RecordingOverlayTimeline

SIDECAR = {
    "version": RECORDING_OVERLAY_SIDECAR_VERSION,
    "device": {
        "svg_file": "device.svg",
        "path_scale": 2.0,
        "scene_rect": [0.0, 0.0, 20.0, 10.0],
        "electrodes": [
            {"id": "e0", "channel": 0, "points": [[0, 0], [10, 0], [10, 10]]},
            {"id": "e1", "channel": None, "points": [[10, 0], [20, 0], [20, 10]]},
        ],
    },
    "started_at": 1700000000.5,
    "disabled_channels": [7],
    "events": [
        {"t_ms": 0, "channels": [1]},
        {"t_ms": 500, "channels": [1, 2]},
        {"t_ms": 1200, "channels": []},
    ],
}


def test_channels_at_holds_each_event_until_the_next():
    timeline = RecordingOverlayTimeline.from_dict(SIDECAR)

    assert timeline.channels_at(0) == {1}
    assert timeline.channels_at(499) == {1}
    assert timeline.channels_at(500) == {1, 2}
    assert timeline.channels_at(1199.5) == {1, 2}
    assert timeline.channels_at(1200) == set()
    assert timeline.channels_at(10_000) == set()


def test_channels_at_is_empty_before_the_first_event_and_without_events():
    assert RecordingOverlayTimeline.from_dict(SIDECAR).channels_at(-1) == set()
    assert RecordingOverlayTimeline().channels_at(0) == set()


def test_events_from_raw_collapse_pre_origin_entries_and_deduplicate():
    raw_events = [
        (9.0, [1]),
        (9.5, [1, 2]),  # before the origin: only the last one counts
        (10.2, []),  # clear-then-update in one millisecond ...
        (10.2002, [3]),  # ... keeps the later state
        (10.5, [3]),  # unchanged: not recorded twice
        (11.0, [3, 4]),
    ]

    assert RecordingOverlayTimeline.events_from_raw(raw_events, 10.0) == [
        {"t_ms": 0, "channels": [1, 2]},
        {"t_ms": 200, "channels": [3]},
        {"t_ms": 1000, "channels": [3, 4]},
    ]


def test_sidecar_round_trip_through_json():
    timeline = RecordingOverlayTimeline.from_dict(json.loads(json.dumps(SIDECAR)))

    assert timeline.to_dict() == SIDECAR
