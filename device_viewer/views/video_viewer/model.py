"""Qt-free HasTraits model for the recordings viewer pane: the browsed
folder, its discovered recordings, playback state, and the raw-vs-aligned
display toggle. Mutated only on the GUI thread (buttons, the canvas's
player callbacks), so no Qt bridging is needed.
"""
from traits.api import (
    Bool, Directory, Event, HasTraits, Int, List, Property, Range, Str,
)


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
    #: (position_ms, (x, y, w, h)) keyframes in the ALIGNED view's scene
    #: coordinates, sorted by time. Each keyframe's region holds until the
    #: next one, so drawing regions at different times makes the export's
    #: crop follow the action frame to frame. Empty = no crop.
    roi_keyframes = List()

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

    def set_roi_keyframe(self, position_ms, region):
        """Add (or replace) the region keyframe at ``position_ms``.
        ``region`` is an (x, y, w, h) tuple in aligned-scene coordinates."""
        keyframes = [(ms, rect) for ms, rect in self.roi_keyframes
                     if ms != position_ms]
        keyframes.append((int(position_ms), tuple(region)))
        keyframes.sort(key=lambda keyframe: keyframe[0])
        self.roi_keyframes = keyframes
