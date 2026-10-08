# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Controller for the image viewer pane: turns toolbar events into model
mutations, loads whatever ``current_path`` points at, keeps the dropdown /
seek slider / path selection in sync, and rescans the browsed folder
(requested by the pane's poll timer).

Loading is asynchronous, latest-wins: ``current_path`` changes replace
the loader thread's single pending request, so dragging the seek slider
never decodes the frames dragged past and never blocks the GUI thread.
The loader thread also renders the display frame (corrections plus the
8-bit window), and display-window / correction edits re-render there the
same way, so a dragged contrast slider only ever renders its newest
window. Finished renders land through ``drain_loaded()`` (the dock pane's
drain timer) and a small LRU cache of decoded frames spares re-decoding
recently viewed ones.
Folder discovery runs the same way on its own worker: requested
rescans are latest-wins and their results land through
``drain_discovered()``.
"""

# Standard library imports.
import queue
import threading
from collections import OrderedDict
from pathlib import Path

# Third-party imports.
import numpy as np

# Enthought library imports.
from pyface.api import OK, DirectoryDialog
from traits.api import Any, Bool, Callable, Instance, Int, observe
from traitsui.api import Controller

# Microdrop utils imports.
from microdrop_utils.file_handler import open_file

# Local imports.
from .consts import DISCOVERY_POLL_INTERVAL_MS, IMAGE_CACHE_FRAMES
from .discovery import (
    CaptureFolderWatch,
    CaptureReadiness,
    current_captures_directory,
    discover_experiments,
    file_signature,
)
from .display import load_image_array, render_display_frame
from .latest_wins_worker import LatestWinsWorker
from .model import (
    BURST_FILTER_ALL,
    IMAGE_FILTER_ALL,
    IMAGE_GROUP_ALL,
    ImageViewerModel,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class ImageViewerController(Controller):
    """All image loading and navigation funnels through
    ``model.current_path`` — the ONE loader below turns it into pixels.
    The dropdown and seek slider both converge on it (traits only notify
    on real changes, so the cross-sync naturally terminates)."""

    model = Instance(ImageViewerModel)

    #: Zero-arg callable returning the contributed IMAGE_FILTERS; resolved
    #: on every rescan so a hot-loaded plugin's filter shows up live.
    image_filters_source = Callable(lambda: [])

    #: One-shot "what to show" hint consumed by the burst-selection
    #: observer ("first"/"last"/"keep"); set by rescan / home / folder
    #: handlers before they change ``selected_burst``.
    _pending_show = Any(None)

    #: Decoded frames, path -> array, newest last; bounded by
    #: IMAGE_CACHE_FRAMES so recently viewed frames re-display instantly.
    _decoded_cache = Instance(OrderedDict, ())

    #: (path, array | None, settings, (corrected, display) | None)
    #: results from the loader thread, applied on the GUI thread by
    #: drain_loaded().
    _load_results = Instance(queue.SimpleQueue, ())

    #: The newest not-yet-started (path, decoded array | None, settings)
    #: request, None when there is none. The loader always takes this and
    #: only this, so frames the slider dragged past are skipped.
    _pending_load = Any(None)

    #: The display settings of the newest request — a window edit under
    #: auto-contrast changes nothing on screen, so it is not re-rendered.
    _requested_settings = Any(None)

    _pending_load_lock = Instance(object)
    _load_wakeup = Instance(object)
    _load_worker = Instance(object)

    #: (path, file_signature) of the displayed image whose load failed,
    #: or None. The failure is not final: a capture caught mid-write
    #: loads once the file changes, so each rescan retries it then.
    _failed_load = Any(None)

    #: Keeps files still being written out of discovery.
    _capture_readiness = Instance(CaptureReadiness)

    def __capture_readiness_default(self):
        return CaptureReadiness(settle_seconds=DISCOVERY_POLL_INTERVAL_MS / 1000)

    #: Skips re-walking the browsed folder while nothing in it changed.
    _capture_folders = Instance(CaptureFolderWatch, ())

    #: Runs requested rescans' discovery off the GUI thread.
    _discovery_worker = Instance(LatestWinsWorker)

    #: Requested rescans so far — each request's sequence number.
    _rescan_requests = Int(0)

    #: (sequence number, (burst index, show)) — the jump to make once the
    #: rescan with that number (or a later one) has been applied; None
    #: when there is none.
    _pending_jump = Any(None)

    #: New captures landed while the analysis model held the view: follow
    #: them once the hold ends.
    _follow_deferred = Bool(False)

    def __pending_load_lock_default(self):
        return threading.Lock()

    def __discovery_worker_default(self):
        return LatestWinsWorker(work=self._discover_request, name="image-discovery")

    def __load_wakeup_default(self):
        return threading.Event()

    # ------------------------------------------------------------------ #
    # Toolbar events                                                       #
    # ------------------------------------------------------------------ #
    @observe("model:directory_button")
    def _pick_directory(self, event):
        # Start in the Experiments root (captures -> experiment -> root).
        captures = current_captures_directory()
        dialog = DirectoryDialog(
            default_path=str(captures.parent.parent) if captures else "",
            message="Select Images Directory",
        )

        # If the user clicks 'OK', update the hidden directory trait
        if dialog.open() == OK:
            self.model.directory = dialog.path
            logger.info(f"Image Viewer: Directory --> {self.model.directory}")

    @observe("model:directory")
    def _browse_directory(self, event):
        """A newly chosen folder: discover its bursts and start at the
        first burst's first image. A cleared directory is the home
        button's reset — it drives the rescan itself (and lands on the
        newest instead)."""
        if not event.new:
            return
        self.request_rescan(jump=(0, "first"))

    @observe("model:home_button")
    def _return_to_experiment_captures(self, event):
        """Back to the ongoing experiment: follow its captures folder
        again and show the newest burst's newest image (so new captures
        auto-follow)."""
        self.model.directory = ""
        self.request_rescan(jump=(-1, "last"))

    @observe("model:open_folder_button")
    def _open_images_folder(self, event):
        """Show the folder the displayed image sits in (the browsed folder
        before one loads) in the system file browser."""
        if self.model.current_path:
            folder = Path(self.model.current_path).parent
        else:
            folder = self._scan_directory()

        if folder is None or not folder.is_dir():
            logger.warning(f"No images folder to open: {folder}")
            return

        open_file(str(folder))

    def _jump_to_burst(self, index, show):
        """Land on ``bursts[index]`` showing its first/last image."""
        names = self.model.burst_names
        if not names:
            return
        target = names[index]
        if self.model.selected_burst != target:
            self._pending_show = show
            self.model.selected_burst = target
        else:
            self._refresh_visible(show)

    # ------------------------------------------------------------------ #
    # Experiment dropdown / experiment slider                              #
    # ------------------------------------------------------------------ #
    @observe("model:selected_experiment")
    def _experiment_selected(self, event):
        """Experiment picked (dropdown or slider): sync the slider and
        repoint the viewer at that experiment's captures — the
        ``directory`` observer then rescans and jumps to the first burst."""
        names = self.model.experiment_names
        if event.new in names:
            self.model.experiment_index = names.index(event.new)
        captures = self.model.experiment_captures(event.new)
        if captures is not None:
            self.model.directory = str(captures)

    @observe("model:experiment_index")
    def _experiment_seek(self, event):
        names = self.model.experiment_names
        if 0 <= event.new < len(names):
            self.model.selected_experiment = names[event.new]

    @observe("model:fit_button")
    def _fit(self, event):
        self.model.fit_request = True

    @observe("model:zoom_in_button")
    def _zoom_in(self, event):
        self.model.zoom_request = 1

    @observe("model:zoom_out_button")
    def _zoom_out(self, event):
        self.model.zoom_request = -1

    @observe("model:previous_button")
    def _previous(self, event):
        self.step(-1)

    @observe("model:next_button")
    def _next(self, event):
        self.step(1)

    def step(self, step):
        """Show the adjacent image, traversing the WHOLE Image Group: within
        the current capture session normally, and across session boundaries
        when the session's images are exhausted — next past the last image
        enters the next session's first image, previous before the first
        enters the previous session's last. Wraps around the group's
        sessions. Also the slideshow tick."""
        paths = self.model.paths
        if not paths:
            return
        index = self.model.path_index()
        if index is None:
            # Displaying an image from outside the list: enter it at the
            # near end.
            self.model.current_path = str(paths[0] if step > 0 else paths[-1])
            return
        new_index = index + step
        if 0 <= new_index < len(paths):
            self.model.current_path = str(paths[new_index])
        elif new_index >= len(paths):
            self._step_to_adjacent_group(1, "first")
        else:
            self._step_to_adjacent_group(-1, "last")

    def _step_to_adjacent_group(self, direction, show):
        """Move to the next/previous capture session (wrapping) and show its
        first/last image. With the "All" choice (or a single group) the
        visible list already spans everything: wrap within it."""
        if self.model.selected_burst == BURST_FILTER_ALL or len(self.model.bursts) <= 1:
            paths = self.model.paths
            self.model.current_path = str(paths[0] if direction > 0 else paths[-1])
            return
        group_index = (self.model.burst_index - 1 + direction) % len(self.model.bursts)
        self._jump_to_burst(group_index + 1, show)

    # ------------------------------------------------------------------ #
    # Image Group dropdown                                                 #
    # ------------------------------------------------------------------ #
    @observe("model:selected_image_group")
    def _image_group_selected(self, event):
        """Image Group picked: list its Capture Sessions, staying on the
        same session when the group has one, else landing on the newest
        session's newest image."""
        self.model.bursts = self.model.image_group_bursts(event.new)
        self._refresh_filter_names()
        names = self.model.burst_names

        if not names:
            self.model.paths = []
            self.model.selected_image = ""
            return

        if self.model.selected_burst in names:
            self.model.burst_index = names.index(self.model.selected_burst)
            self._refresh_visible("first")
        else:
            self._jump_to_burst(-1, "last")

    def _pick_image_group(self):
        """Keep the selected Image Group while it exists; otherwise "All"
        ('' when nothing is discovered)."""
        names = self.model.image_group_names

        if self.model.selected_image_group in names:
            return self.model.selected_image_group

        return IMAGE_GROUP_ALL if names else ""

    # ------------------------------------------------------------------ #
    # Capture Session dropdown / session slider / image filter             #
    # ------------------------------------------------------------------ #
    @observe("model:selected_burst")
    def _burst_selected(self, event):
        """Burst picked (dropdown, slider, or a programmatic jump):
        sync the slider and rebuild the visible image list. A plain user
        pick starts at the burst's first image; rescan/home hand a
        different intent through ``_pending_show``."""
        show = self._pending_show or "first"
        self._pending_show = None
        names = self.model.burst_names
        if event.new in names:
            self.model.burst_index = names.index(event.new)
        self._refresh_visible(show)

    @observe("model:burst_index")
    def _burst_seek(self, event):
        names = self.model.burst_names
        if 0 <= event.new < len(names):
            self.model.selected_burst = names[event.new]

    @observe("model:selected_filter")
    def _image_filtered(self, event):
        """Filter change: keep the displayed image when it survives the
        filter, else fall to the first surviving one."""
        self._refresh_visible("keep")

    def _visible_paths(self):
        """The selected burst's images through the image filter."""
        return self.model.visible_of(self.model.burst_paths(self.model.selected_burst))

    def _refresh_visible(self, show):
        """Rebuild ``model.paths`` and pick what to display: "first" /
        "last" of the visible list, or "keep" (stay on the current image
        when it is still visible, else fall to the first)."""
        paths = self._visible_paths()
        if paths != self.model.paths:
            self.model.paths = paths
        if not paths:
            self.model.selected_image = ""
            return
        if show == "keep" and self.model.path_index() is not None:
            self._sync_selection()
            return
        target = paths[-1] if show == "last" else paths[0]
        if self.model.current_path != str(target):
            self.model.current_path = str(target)
        else:
            self._sync_selection()

    def object_filter_label_changed(self, info):
        """Name the filter row after the contributed filter (e.g.
        "Wavelength"): TraitsUI item labels are static, so the row's label
        widget is retitled. Also runs once when the UI is built."""
        label_control = info.selected_filter.label_control

        if label_control is not None and info.object.filter_label:
            label_control.setText(f"{info.object.filter_label}:")

    # ------------------------------------------------------------------ #
    # Dropdown / seek-slider selection                                     #
    # ------------------------------------------------------------------ #
    @observe("model:selected_image")
    def _select_by_name(self, event):
        for path in self.model.paths:
            if path.name == event.new:
                self.model.current_path = str(path)
                return

    @observe("model:image_index")
    def _seek(self, event):
        if 0 <= event.new < len(self.model.paths):
            self.model.current_path = str(self.model.paths[event.new])

    def _sync_selection(self):
        """Point the dropdown and seek slider at the displayed image."""
        index = self.model.path_index()
        if index is not None:
            self.model.image_index = index
            self.model.selected_image = self.model.paths[index].name
        else:
            self.model.selected_image = ""

    # ------------------------------------------------------------------ #
    # Loading                                                              #
    # ------------------------------------------------------------------ #
    @observe("model:current_path")
    def _load_current_path(self, event):
        self._failed_load = None
        self._render_current_path()

    @observe(
        "model:auto_contrast, model:window_min, model:window_max, "
        "model:roi_analysis:session, "
        "model:roi_analysis:session:ball:enabled, "
        "model:roi_analysis:session:ball:radius_px, "
        "model:roi_analysis:session:perspective:enabled, "
        "model:roi_analysis:session:perspective:matrix"
    )
    def _display_settings_changed(self, event):
        if self._display_settings() != self._requested_settings:
            self._render_current_path()

    def _display_settings(self):
        """The window and corrections a frame renders with, snapshotted
        on the GUI thread as :func:`render_display_frame`'s trailing
        arguments — the loader thread never reads traits."""
        model = self.model
        session = model.roi_analysis.session
        window = None if model.auto_contrast else (model.window_min, model.window_max)

        return (
            model.auto_contrast,
            window,
            session.ball.effective_radius(),
            session.perspective.effective_matrix(),
        )

    def _render_current_path(self):
        """Hand the loader thread the displayed path to render with the
        current settings, decoding it first unless it is cached. Latest
        wins: this replaces any not-yet-started request, so frames the
        slider dragged past are never decoded at all."""
        path = self.model.current_path

        if not path:
            return

        array = self._decoded_cache.get(path)

        if array is None:
            self.model.info_text = f"Loading {Path(path).name}…"
        else:
            self._decoded_cache.move_to_end(path)

        self._requested_settings = self._display_settings()

        with self._pending_load_lock:
            self._pending_load = (path, array, self._requested_settings)
            self._load_wakeup.set()

        self._ensure_load_worker()

    def _ensure_load_worker(self):
        if self._load_worker is not None and self._load_worker.is_alive():
            return
        self._load_worker = threading.Thread(target=self._run_loader, daemon=True)
        self._load_worker.start()

    def _run_loader(self):
        """Daemon loader: decode the newest pending path unless it came
        decoded, render its display frame, report on the results queue,
        wait for the next request."""
        while True:
            self._load_wakeup.wait()

            with self._pending_load_lock:
                request = self._pending_load
                self._pending_load = None
                self._load_wakeup.clear()

            if request is None:
                continue

            path, array, settings = request
            rendered = None

            if array is None:
                try:
                    array = load_image_array(path)
                except Exception as error:
                    logger.warning(f"Image decode failed for {path}: {error}")

            if array is not None:
                try:
                    rendered = render_display_frame(array, *settings)
                except Exception as error:
                    logger.warning(f"Image render failed for {path}: {error}")

            self._load_results.put((path, array, settings, rendered))

    def drain_loaded(self):
        """Called by the dock pane's drain timer (GUI thread): apply
        finished renders. Only the currently displayed path is shown, but
        every successful decode enters the cache. A render whose settings
        have since moved is still shown: the newer request is already
        queued behind it, so a dragged slider previews as it goes."""
        while True:
            try:
                path, array, _settings, rendered = self._load_results.get_nowait()
            except queue.Empty:
                return

            if array is not None:
                self._decoded_cache[path] = array
                self._decoded_cache.move_to_end(path)

                while len(self._decoded_cache) > IMAGE_CACHE_FRAMES:
                    self._decoded_cache.popitem(last=False)

            if path != self.model.current_path:
                continue

            if rendered is None:
                logger.error(f"Could not load image: {path}")
                self.model.info_text = "Could not load image"
                self._failed_load = (path, file_signature(path))
                continue

            self._apply_loaded(path, array, *rendered)

    def _apply_loaded(self, path, array, corrected, display):
        is_new_image = array is not self.model.array

        # The canvas draws display_frame and refits on array, so the
        # frame must be in place before array announces a new image.
        self.model.corrected_array = corrected
        self.model.display_frame = display
        self.model.array = array

        if not is_new_image:
            return

        bits = 16 if array.dtype == np.uint16 else 8
        kind = "gray" if array.ndim == 2 else "RGB"
        self.model.info_text = (
            f"{Path(path).name} - {array.shape[1]}x{array.shape[0]} {bits}-bit {kind}"
        )
        self._sync_selection()
        logger.info(f"Loaded image: {path} ({bits}-bit {kind})")

    # ------------------------------------------------------------------ #
    # Folder discovery (requested by the pane's poll timer)                #
    # ------------------------------------------------------------------ #
    def _scan_directory(self):
        return _resolve_scan_directory(self.model.directory)

    def request_rescan(self, jump=None):
        """Rescan off the GUI thread; the result is applied by
        drain_discovered(). ``jump`` — (burst index, show) — is made once
        it has been (the folder and home buttons' landing)."""
        self._rescan_requests += 1

        if jump is not None:
            self._pending_jump = (self._rescan_requests, jump)

        self._discovery_worker.submit((self._rescan_requests, self.model.directory))

    def _discover_request(self, request):
        """Worker side of request_rescan: reads no traits, only the
        request's snapshot of ``model.directory``."""
        number, directory = request
        scan_directory = _resolve_scan_directory(directory)

        return number, directory, scan_directory, *self._discover(scan_directory)

    def _discover(self, scan_directory):
        """The experiment list and ``scan_directory``'s Image Groups."""
        return (
            discover_experiments(),
            self._capture_folders.image_groups(scan_directory, self._capture_readiness),
        )

    def drain_discovered(self):
        """Called by the dock pane's drain timer (GUI thread): apply
        finished rescans, then any jump waiting on them. A rescan of a
        folder the user has since left is dropped — the rescan the switch
        requested is already queued behind it."""
        for result in self._discovery_worker.drain():
            number, directory, scan_directory, *discovered = result

            if directory != self.model.directory:
                continue

            self._apply_discovery(scan_directory, *discovered)

            if self._pending_jump is not None and self._pending_jump[0] <= number:
                _number, jump = self._pending_jump
                self._pending_jump = None
                self._jump_to_burst(*jump)

    def capture_saved(self, path):
        """A capture's writer reports ``path`` complete: show it without
        waiting out the settle time, then rescan."""
        self._capture_readiness.mark_complete(path)
        self.request_rescan()

    def _retry_failed_load(self):
        """Reload the displayed image whose load failed once the file
        has changed since — it was most likely caught mid-write."""
        path, signature = self._failed_load

        if file_signature(path) == signature:
            return

        self._failed_load = None
        self._render_current_path()

    def rescan(self):
        """Rescan on the calling thread (request_rescan is the GUI's
        path): sync with the browsed folder's Image Groups and their
        Capture Sessions."""
        scan_directory = self._scan_directory()
        self._apply_discovery(scan_directory, *self._discover(scan_directory))

    def _apply_discovery(self, directory, experiments, image_groups):
        """Apply a rescan: a newly landed session / image is followed
        automatically unless the user is parked on an older one. Also
        refreshes the image-filter choices from what the filenames embed,
        and retries a failed load whose file has changed."""
        if self._failed_load is not None:
            self._retry_failed_load()

        # The Experiments dropdown tracks newly created experiments; the
        # user's selection is left untouched.
        if experiments != self.model.experiments:
            self.model.experiments = experiments

        filters = self.image_filters_source()
        image_filter = filters[0] if filters else None

        if image_filter is not self.model.image_filter:
            self.model.image_filter = image_filter
            self._refresh_filter_names()

        self.model.browsed_directory = str(directory) if directory else ""

        if image_groups == self.model.image_groups:
            return

        # "Following newest" = showing the newest visible image of the
        # newest burst (or nothing yet) — those users ride along as new
        # captures land; anyone parked elsewhere stays parked.
        on_all = self.model.selected_burst == BURST_FILTER_ALL
        following_newest = (
            self._follow_deferred
            or not self.model.current_path
            or not self.model.paths
            or (on_all and self.model.current_path == str(self.model.paths[-1]))
            or (
                not on_all
                and self.model.burst_names
                and self.model.selected_burst == self.model.burst_names[-1]
                and self.model.current_path == str(self.model.paths[-1])
            )
        )
        self.model.image_groups = image_groups
        group = self._pick_image_group()

        if group != self.model.selected_image_group:
            # The group observer lists its sessions and lands on the newest.
            self.model.selected_image_group = group
            return

        self.model.bursts = self.model.image_group_bursts(group)
        self._refresh_filter_names()

        names = self.model.burst_names
        if not names:
            self.model.paths = []
            self.model.selected_image = ""
            return
        if following_newest and self.model.roi_analysis.holds_view:
            self._follow_deferred = True
            self._refresh_visible("keep")
        elif following_newest:
            self._follow_newest()
        elif self.model.selected_burst not in names:
            # The parked burst vanished (folder pruned): fall to newest.
            self._jump_to_burst(-1, "first")
        else:
            self._refresh_visible("keep")

    def _follow_newest(self):
        self._follow_deferred = False

        if self.model.selected_burst == BURST_FILTER_ALL:
            self._refresh_visible("last")
        else:
            self._jump_to_burst(-1, "last")

    @observe("model:roi_analysis:holds_view")
    def _follow_after_hold(self, event):
        if self._follow_deferred and not event.new:
            self._follow_newest()

    def _refresh_filter_names(self):
        """Offer "All" plus every filter value the discovered files carry;
        a selection that no longer exists falls back to "All"."""
        detected = sorted(
            {
                value
                for _name, paths in self.model.bursts
                for value in map(self.model.filter_value, paths)
                if value
            }
        )
        self.model.filter_names = [IMAGE_FILTER_ALL] + detected

        if self.model.selected_filter not in self.model.filter_names:
            self.model.selected_filter = IMAGE_FILTER_ALL


def _resolve_scan_directory(directory):
    """The folder a rescan walks: ``directory`` when one is browsed ('' =
    follow the current experiment's captures folder)."""
    if directory:
        return Path(directory)

    return current_captures_directory()
