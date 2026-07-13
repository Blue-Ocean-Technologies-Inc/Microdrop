"""Dock pane for viewing recorded videos.

Plays the raw recordings the native recorder writes, with a
Device-Aligned toggle that reconstructs the perspective-warped view from
the recording's ``.transform.json`` sidecar — the same alignment the live
device view showed while recording. Regions of interest can be keyframed
over playback time (Edit Region mode) in EITHER view — raw or aligned,
sidecar or not — and the matching rendition (aligned and/or cropped)
exported to a file next to the recording.
"""
import json
from pathlib import Path

from pyface.gui import GUI
from pyface.tasks.api import TraitsDockPane
from pyface.api import DirectoryDialog, OK
from traits.api import Any, Bool, Instance, Button, observe
from traitsui.api import (
    CustomEditor, EnumEditor, HGroup, Item, Readonly, UItem, VGroup, View,
)


from microdrop_application.helpers import get_current_experiment_directory
from microdrop_style.icons.icons import (
    ICON_CROP, ICON_DELETE, ICON_FIT_SCREEN, ICON_FOLDER_OPEN, ICON_HOME,
    ICON_PAUSE, ICON_PLAY, ICON_REFRESH, ICON_SAVE, ICON_TRANSFORM,
)
from microdrop_utils.traitsui_qt_helpers import (
    IconButtonEditor, IconToggleEditor,
)

from ...consts import (
    PKG, RECORDINGS_DIR_NAME, RECORDING_TRANSFORM_SIDECAR_SUFFIX,
    recording_state_model,
)
from .model import VideoViewerModel
from .video_canvas import video_canvas_factory
from .video_export import AlignedVideoExporter


from logger.logger_service import get_logger
logger = get_logger(__name__)

#: Recording containers the viewer lists (native recorder writes .mkv,
#: like the legacy ffmpeg-pipe recorder; .mp4 covers stray files).
RECORDING_GLOBS = ("*.mp4", "*.mkv")

#: Region-of-interest keyframes saved next to each recording, so a crop
#: setup survives reloads and exports stay reproducible.
ROI_SIDECAR_SUFFIX = ".roi.json"


class VideoViewerDockPane(TraitsDockPane):
    """Viewer for recorded videos (raw or device-aligned playback)."""

    id = PKG + ".video_viewer.dock_pane"
    name = "Recording Viewer"

    model = Instance(VideoViewerModel)
    # Compact icon toolbar (words live in the tooltips), mirroring the
    # fluorescence image viewer's button row.
    view = View(
    VGroup(
        HGroup(
            UItem("pane.directory_button", editor=IconButtonEditor(
                glyph=ICON_FOLDER_OPEN,
                tooltip="Choose the recordings folder (defaults to the "
                        "current experiment's recordings)")),
            UItem("pane.home_button", editor=IconButtonEditor(
                glyph=ICON_HOME,
                tooltip="Back to the current experiment's recordings "
                        "(newest recording)")),
            UItem("pane.refresh_button", editor=IconButtonEditor(
                glyph=ICON_REFRESH,
                tooltip="Re-scan the current folder for new recordings")),
            UItem("pane.fit_button", editor=IconButtonEditor(
                glyph=ICON_FIT_SCREEN,
                tooltip="Fit the video to the pane (clears the saved "
                        "zoom/pan)")),
            UItem("aligned", editor=IconToggleEditor(
                on_glyph=ICON_TRANSFORM, off_glyph=ICON_TRANSFORM,
                tooltip="Show the device-aligned (perspective-warped) "
                        "view from the recording's transform sidecar"),
                enabled_when="has_transform"),
            UItem("roi_edit_mode", editor=IconToggleEditor(
                on_glyph=ICON_CROP, off_glyph=ICON_CROP,
                tooltip="Edit the region of interest: drag on the video "
                        "to set the region at the current time (works in "
                        "the raw and the device-aligned view)"),
                enabled_when="current_path"),
            UItem("pane.clear_roi_button", editor=IconButtonEditor(
                glyph=ICON_DELETE,
                tooltip="Clear all region-of-interest keyframes"),
                enabled_when="roi_keyframes"),
            UItem("pane.export_button", editor=IconButtonEditor(
                glyph=ICON_SAVE,
                tooltip="Save the current rendition (device-aligned "
                        "and/or region-cropped) next to the recording"),
                enabled_when="current_path and not exporting "
                             "and (aligned or roi_keyframes)"),
            Readonly("export_status", show_label=False),
        ),
        Item("selected_video", label="Recording",
             editor=EnumEditor(name="object.video_names")),
        UItem("current_path", editor=CustomEditor(video_canvas_factory)),
        HGroup(
            UItem("playing", editor=IconToggleEditor(
                on_glyph=ICON_PAUSE, off_glyph=ICON_PLAY,
                tooltip="Play / pause"),
                enabled_when="current_path"),
            UItem("position_ms", enabled_when="current_path"),
            Readonly("time_text", show_label=False),
        ),
    ),
    resizable=True,
)

    # Toolbar buttons (view elements, so they live on the PANE and the
    # View references them via the "pane." prefix).
    directory_button = Button()
    #: Back to the current experiment's recordings folder.
    home_button = Button()
    #: Re-scan the browsed folder for new recordings.
    refresh_button = Button()
    #: Refit the canvas to the frame (clears the persisted zoom/pan).
    fit_button = Button()
    clear_roi_button = Button()
    #: Export the device-aligned (+ ROI-cropped) rendition.
    export_button = Button()

    def traits_init(self):
        self.model = VideoViewerModel()
        # Auto-refresh when a recording finishes: the camera widget flips
        # this shared state AFTER the recorder's stopped signal, so the
        # file and its transform sidecar are already on disk.
        recording_state_model.observe(self._on_recording_state_changed,
                                      "recording")

    def destroy(self):
        recording_state_model.observe(self._on_recording_state_changed,
                                      "recording", remove=True)
        super().destroy()

    def _on_recording_state_changed(self, event):
        if event.old and not event.new:
            # Recording just finished — recordings land in the current
            # experiment's folder: point there and pick up the new file
            # (discovery auto-selects the newest recording).
            self._go_home()

    @observe("model")
    def _model_updated(self, event):
        self._go_home()

    # ------------------------------------------------------------------ #
    # Discovery                                                            #
    # ------------------------------------------------------------------ #
    @observe("model:directory")
    def _refresh_recordings(self, event=None):
        directory = Path(self.model.directory) if self.model.directory else None
        recordings = []
        if directory is not None and directory.is_dir():
            for pattern in RECORDING_GLOBS:
                recordings.extend(directory.glob(pattern))
            recordings.sort(key=lambda path: path.stat().st_mtime)
        self.model.recordings = recordings
        if recordings:
            # Newest recording is usually the one of interest.
            self.model.selected_video = recordings[-1].name
        else:
            self.model.selected_video = ""
            self.model.current_path = ""

    @observe("model:selected_video")
    def _load_selected(self, event):
        for path in self.model.recordings:
            if path.name == self.model.selected_video:
                self.model.current_path = str(path)
                self._load_roi_sidecar(path)
                return

    # ------------------------------------------------------------------ #
    # Region-of-interest persistence (per recording)                       #
    # ------------------------------------------------------------------ #
    #: Guards the ROI sidecar sync against echoing its own load.
    _loading_roi = Bool(False)

    def _load_roi_sidecar(self, video_path):
        roi_path = Path(video_path).with_suffix(ROI_SIDECAR_SUFFIX)
        keyframes, roi_aligned = [], True
        if roi_path.is_file():
            try:
                data = json.loads(roi_path.read_text())
                if isinstance(data, dict):
                    roi_aligned = bool(data.get("aligned", True))
                    raw_keyframes = data.get("keyframes", [])
                else:
                    # Legacy bare-list sidecar: regions were always drawn
                    # in the aligned view back then.
                    raw_keyframes = data
                keyframes = [(int(ms), tuple(region))
                             for ms, region in raw_keyframes]
            except Exception as e:
                logger.warning(f"Unreadable ROI sidecar {roi_path}: {e}")
        self._loading_roi = True
        try:
            self.model.roi_aligned = roi_aligned
            self.model.roi_keyframes = keyframes
        finally:
            self._loading_roi = False

    @observe("model:roi_keyframes")
    def _persist_roi_sidecar(self, event):
        if self._loading_roi or not self.model.current_path:
            return
        roi_path = Path(self.model.current_path).with_suffix(ROI_SIDECAR_SUFFIX)
        try:
            if self.model.roi_keyframes:
                roi_path.write_text(json.dumps({
                    "aligned": self.model.roi_aligned,
                    "keyframes": [[ms, list(region)]
                                  for ms, region in self.model.roi_keyframes],
                }))
            elif roi_path.is_file():
                roi_path.unlink()
        except Exception as e:
            logger.warning(f"Could not persist ROI sidecar {roi_path}: {e}")

    @observe("clear_roi_button")
    def _clear_roi(self, event):
        self.model.roi_keyframes = []

    @observe("fit_button")
    def _request_fit(self, event):
        self.model.fit_request = True

    # ------------------------------------------------------------------ #
    # Aligned export                                                       #
    # ------------------------------------------------------------------ #
    #: The running exporter (kept referenced for its lifetime).
    _exporter = Any()

    @observe("export_button")
    def _export_aligned_video(self, event):
        model = self.model
        if model.exporting or not model.current_path:
            return
        # The regions' space decides the rendition (they only make sense in
        # the view they were drawn in); with no regions, export whatever
        # view is displayed.
        export_aligned = (model.roi_aligned if model.roi_keyframes
                          else model.aligned)
        sidecar = None
        if export_aligned:
            sidecar_path = Path(model.current_path).with_suffix(
                RECORDING_TRANSFORM_SIDECAR_SUFFIX)
            try:
                sidecar = json.loads(sidecar_path.read_text())
            except Exception as e:
                model.export_status = f"No usable transform sidecar: {e}"
                return
        model.exporting = True
        model.export_status = "Exporting…"
        self._exporter = AlignedVideoExporter(
            model.current_path, sidecar, list(model.roi_keyframes),
            aligned=export_aligned)
        # Exporter signals fire on its worker thread; marshal every trait
        # write back onto the GUI thread.
        self._exporter.progress.connect(
            lambda text: GUI.invoke_later(
                setattr, model, "export_status", text))
        self._exporter.finished.connect(
            lambda path: GUI.invoke_later(
                model.trait_set, exporting=False,
                export_status=f"Saved {Path(path).name}"))
        self._exporter.failed.connect(
            lambda message: GUI.invoke_later(
                model.trait_set, exporting=False,
                export_status=f"Export failed: {message}"))
        self._exporter.start()

    # ------------------------------------------------------------------ #
    # Toolbar buttons                                                      #
    # ------------------------------------------------------------------ #
    @observe("directory_button")
    def _pick_directory(self, event):
        dialog = DirectoryDialog(default_path=self.model.directory or "")
        if dialog.open() == OK:
            self.model.directory = dialog.path

    @observe("home_button")
    def _on_home(self, event):
        self._go_home()

    @observe("refresh_button")
    def _on_refresh(self, event):
        self._refresh_recordings()

    def _go_home(self):
        """Point at the current experiment's recordings folder."""
        try:
            experiment_directory = get_current_experiment_directory()
        except Exception as e:
            logger.debug(f"No current experiment directory: {e}")
            return
        if experiment_directory:
            recordings_directory = Path(experiment_directory) / RECORDINGS_DIR_NAME
            if str(recordings_directory) == self.model.directory:
                self._refresh_recordings()   # same folder: re-scan for new files
            else:
                self.model.directory = str(recordings_directory)

