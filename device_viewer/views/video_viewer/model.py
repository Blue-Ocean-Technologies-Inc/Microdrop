# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free HasTraits model for the recordings viewer pane: the browsed
folder, its discovered recordings, playback state, the raw-vs-aligned
display toggle and the device overlay drawn over it. Mutated only on the
GUI thread (buttons, the canvas's player callbacks), so no Qt bridging is
needed.
"""

# Enthought library imports.
from traits.api import (
    Bool,
    Directory,
    Event,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Range,
    Str,
    observe,
)

# Local imports.
from ...default_settings import (
    actuated_electrodes_key,
    default_alphas,
    electrode_outline_key,
)
from ...models.recording_overlay import RecordingOverlayTimeline
from ...preferences import DeviceViewerPreferences

#: Model traits mirrored to DeviceViewerPreferences as "video_viewer_<name>".
OVERLAY_DISPLAY_TRAITS = [
    "show_device_outline",
    "device_outline_alpha",
    "show_actuations",
    "actuations_alpha",
]


class VideoViewerModel(HasTraits):
    """State for the recorded-video viewer."""

    #: Folder being browsed. '' follows the current experiment's
    #: recordings folder; the folder button points it elsewhere.
    directory = Directory()

    #: Discovered recordings in the browsed folder (Path objects),
    #: oldest first.
    recordings = List()

    #: Path of the loaded recording ('' before the first load). Setting it
    #: is the ONE way a video gets shown — the canvas loads it.
    current_path = Str()

    #: Basename choices for the recording dropdown (mirrors ``recordings``).
    video_names = Property(List(Str), observe="recordings.items")

    #: Basename of the loaded recording — the dropdown selection.
    selected_video = Str()

    #: True when the loaded recording has an alignment sidecar
    #: (see consts.RECORDING_TRANSFORM_SIDECAR_SUFFIX).
    has_transform = Bool(False)

    #: Show the device-aligned (perspective-warped) view instead of the
    #: raw camera frames. Only meaningful when has_transform.
    aligned = Bool(False)

    # ------------------------------------------------------------------ #
    # Device overlay (from the recording's overlay sidecar)                #
    # ------------------------------------------------------------------ #
    #: The loaded recording's device outline + actuation timeline, or None
    #: when it has no overlay sidecar (see
    #: consts.RECORDING_OVERLAY_SIDECAR_SUFFIX).
    overlay = Instance(RecordingOverlayTimeline)

    #: True when the loaded recording has an overlay sidecar.
    has_overlay = Property(Bool, observe="overlay")

    #: Draw the device's electrode outlines over the device-aligned view,
    #: at device_outline_alpha percent.
    show_device_outline = Bool(False)
    device_outline_alpha = Range(
        0, 100, default_alphas[electrode_outline_key], mode="spinner"
    )

    #: Draw the electrodes actuated at the playback position over the
    #: device-aligned view, at actuations_alpha percent.
    show_actuations = Bool(False)
    actuations_alpha = Range(
        0, 100, default_alphas[actuated_electrodes_key], mode="spinner"
    )

    #: Opacity (0-1) each overlay layer is drawn at; 0 while toggled off.
    outline_opacity = Property(observe="show_device_outline, device_outline_alpha")
    actuations_opacity = Property(observe="show_actuations, actuations_alpha")

    #: Channels actuated at the playback position.
    overlay_actuated_channels = Property(observe="overlay, position_ms")

    #: Where the overlay toggles and alphas persist; None keeps them
    #: in memory only.
    preferences = Instance(DeviceViewerPreferences)

    #: Playback state (the play/pause toggle; the canvas drives the player
    #: and reflects the player's real state back here).
    playing = Bool(False)

    #: Playback position/duration in milliseconds. position_ms doubles as
    #: the seek slider (its upper bound rides the loaded duration).
    duration_ms = Int(0)
    position_ms = Range(0, "duration_ms", 0, mode="slider")

    #: "m:ss / m:ss" readout next to the seek slider.
    time_text = Property(Str, observe="position_ms, duration_ms")

    # ------------------------------------------------------------------ #
    # Region of interest (dynamic: keyframed over playback time)           #
    # ------------------------------------------------------------------ #
    #: (position_ms, (x, y, w, h)) keyframes in the scene coordinates of
    #: the view they were drawn in (see roi_aligned), sorted by time. Each
    #: keyframe's region holds until the next one, so drawing regions at
    #: different times makes the export's crop follow the action frame to
    #: frame. Empty = no crop.
    roi_keyframes = List()

    #: Which view's coordinates the keyframes live in: the device-aligned
    #: scene (True) or the raw frame (False). Regions live in ONE space at
    #: a time — drawing in the other view clears them (the two coordinate
    #: systems don't mix).
    roi_aligned = Bool(True)

    #: Rubber-band ROI drawing mode (the Edit Region toggle): while on,
    #: dragging on the canvas defines the region at the CURRENT position.
    roi_edit_mode = Bool(False)

    #: The keyframe region active at the current playback position (what
    #: the canvas outlines), or None.
    active_roi = Property(observe="roi_keyframes.items, position_ms")

    #: One-shot request to refit the canvas to the frame (also clears the
    #: persisted zoom/pan). Fired by the pane's Fit View button.
    fit_request = Event()

    # Export of the device-aligned (+ ROI-cropped) rendition.
    exporting = Bool(False)
    export_status = Str("")

    def traits_init(self):
        if self.preferences is not None:
            self.trait_set(
                **{
                    name: getattr(self.preferences, f"video_viewer_{name}")
                    for name in OVERLAY_DISPLAY_TRAITS
                }
            )

    @observe(OVERLAY_DISPLAY_TRAITS, post_init=True)
    def _persist_overlay_display(self, event):
        if self.preferences is not None:
            setattr(self.preferences, f"video_viewer_{event.name}", event.new)

    def _get_has_overlay(self):
        return self.overlay is not None

    def _get_outline_opacity(self):
        return self.device_outline_alpha / 100 if self.show_device_outline else 0.0

    def _get_actuations_opacity(self):
        return self.actuations_alpha / 100 if self.show_actuations else 0.0

    def _get_overlay_actuated_channels(self):
        if self.overlay is None:
            return set()

        return self.overlay.channels_at(self.position_ms)

    def _get_video_names(self):
        return [path.name for path in self.recordings]

    def _get_time_text(self):
        def clock(milliseconds):
            seconds = int(milliseconds // 1000)
            return f"{seconds // 60:d}:{seconds % 60:02d}"

        return f"{clock(self.position_ms)} / {clock(self.duration_ms)}"

    def _get_active_roi(self):
        return self.roi_at(self.position_ms)

    def roi_at(self, position_ms):
        """The region holding at ``position_ms`` (stepwise: the latest
        keyframe at or before it). Times BEFORE the first keyframe use the
        first keyframe's region — a single region drawn mid-video means
        "crop the whole video here", not "crop from this moment on"."""
        if not self.roi_keyframes:
            return None
        active = self.roi_keyframes[0][1]
        for keyframe_ms, region in self.roi_keyframes:
            if keyframe_ms > position_ms:
                break
            active = region
        return active

    def set_roi_keyframe(self, position_ms, region, aligned):
        """Add (or replace) the region keyframe at ``position_ms``.
        ``region`` is an (x, y, w, h) tuple in the scene coordinates of the
        view it was drawn in (``aligned``). Drawing in the other view than
        the existing keyframes clears them — the spaces don't mix."""
        if aligned != self.roi_aligned:
            keyframes = []
        else:
            keyframes = [
                (ms, rect) for ms, rect in self.roi_keyframes if ms != position_ms
            ]
        self.roi_aligned = aligned
        keyframes.append((int(position_ms), tuple(region)))
        keyframes.sort(key=lambda keyframe: keyframe[0])
        self.roi_keyframes = keyframes
