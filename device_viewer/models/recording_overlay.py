# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The overlay timeline of one recording: the device's electrode geometry
and the actuated channels over the recording's time, as the device viewer
displayed them. Recorded live alongside the video, written as the
recording's overlay sidecar, and read back by the recording viewer and the
aligned export to redraw the device over the video."""

# Standard library imports.
import bisect
import time
from pathlib import Path

# Third-party imports.
import numpy as np

# Enthought library imports.
from traits.api import (
    Bool,
    Dict,
    Float,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    cached_property,
    observe,
)

# Local imports.
from ..consts import RECORDING_OVERLAY_SIDECAR_VERSION
from .electrodes import Electrodes


class RecordingOverlayTimeline(HasTraits):
    """Device snapshot plus actuation timeline of one recording."""

    #: Live electrodes model whose displayed actuation is recorded; None for
    #: a timeline read back from a sidecar.
    electrodes = Instance(Electrodes)

    #: SVG-path -> scene coordinate scale (ElectrodeLayer.path_scale) the
    #: geometry is snapshotted with.
    path_scale = Float(1.0)

    #: Device snapshot taken at start: SVG file name, path_scale, the
    #: device's scene rect and every electrode's id, channel and outline
    #: points in scene coordinates (the space of the transform sidecar's
    #: scene_bounding_rect).
    device = Dict()

    #: Wall-clock epoch of the recording's time origin.
    started_at = Float()

    #: Channels disabled when the recording started.
    disabled_channels = List(Int)

    #: {"t_ms", "channels"} events, oldest first: the full set of actuated
    #: channels from t_ms (relative to the time origin) on. The first event
    #: is the state at the origin (t_ms 0). Built by stop().
    events = List(Dict)

    #: True between start and stop.
    recording = Bool(False)

    #: time.monotonic() at the recording's first frame (see
    #: mark_time_origin); None until the recorder marks it.
    time_origin = Instance(float)

    #: Event times, for the bisect in channels_at.
    _event_times = Property(List(Int), observe="events.items")

    #: (time.monotonic(), sorted channels) per displayed actuation change
    #: since start, converted to events by stop().
    _raw_events = List()

    @classmethod
    def from_dict(cls, data):
        """A timeline read back from overlay sidecar ``data``."""
        return cls(
            device=data.get("device", {}),
            started_at=data.get("started_at", 0.0),
            disabled_channels=data.get("disabled_channels", []),
            events=data.get("events", []),
        )

    def start(self):
        """Snapshot the device and start logging actuation changes. Call on
        the GUI thread when the recorder is started; the recorder marks the
        time origin later (mark_time_origin)."""
        svg_model = self.electrodes.svg_model
        scale = self.path_scale

        self.device = {
            "svg_file": Path(svg_model.filename).name,
            "path_scale": scale,
            "scene_rect": [
                svg_model.min_x * scale,
                svg_model.min_y * scale,
                (svg_model.max_x - svg_model.min_x) * scale,
                (svg_model.max_y - svg_model.min_y) * scale,
            ],
            "electrodes": [
                {
                    "id": electrode.id,
                    "channel": electrode.channel,
                    # Electrode.path is an object array: round needs floats.
                    "points": np.round(
                        scale * np.asarray(electrode.path, dtype=float), 3
                    ).tolist(),
                }
                for electrode in self.electrodes
            ],
        }

        self.disabled_channels = sorted(self.electrodes.disabled_channels)
        self._raw_events = []
        self.recording = True

        self._log_actuation()

    def mark_time_origin(self):
        """Store the clock at the recording's first frame; only the first
        call counts. Plain assignments only, so a recorder may call it from
        its IO thread."""
        if self.time_origin is None:
            self.started_at = time.time()
            self.time_origin = time.monotonic()

    def stop(self):
        """Stop logging and build ``events`` relative to the time origin
        (none when it was never marked: no frame was recorded). Releases
        the live electrodes model."""
        if not self.recording:
            return

        self.recording = False

        if self.time_origin is not None:
            self.events = self.events_from_raw(self._raw_events, self.time_origin)

        self.electrodes = None

    @staticmethod
    def events_from_raw(raw_events, time_origin):
        """Events from (monotonic seconds, sorted channels) log entries.
        Entries at or before ``time_origin`` collapse into the state at
        t_ms 0 (the last of them). A clear-then-update lands as two entries
        in the same millisecond: the later replaces the earlier, and an
        unchanged set is not recorded twice."""
        events = []

        for timestamp, channels in raw_events:
            t_ms = max(0, round((timestamp - time_origin) * 1000))

            if events and events[-1]["t_ms"] == t_ms:
                events.pop()

            if events and events[-1]["channels"] == channels:
                continue

            events.append({"t_ms": t_ms, "channels": channels})

        return events

    def to_dict(self):
        """The overlay sidecar's contents."""
        return {
            "version": RECORDING_OVERLAY_SIDECAR_VERSION,
            "device": self.device,
            "started_at": self.started_at,
            "disabled_channels": list(self.disabled_channels),
            "events": list(self.events),
        }

    def channels_at(self, t_ms):
        """Channels actuated at ``t_ms`` (the latest event at or before it;
        none before the first)."""
        index = bisect.bisect_right(self._event_times, t_ms)

        if index == 0:
            return set()

        return set(self.events[index - 1]["channels"])

    @cached_property
    def _get__event_times(self):
        return [event["t_ms"] for event in self.events]

    @observe("electrodes.actuated_channels.items")
    def _record_actuation(self, event):
        if self.recording:
            self._log_actuation()

    def _log_actuation(self):
        """Log the displayed actuated set with the raw clock reading."""
        self._raw_events.append(
            (time.monotonic(), sorted(self.electrodes.actuated_channels))
        )
