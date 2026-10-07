# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free HasTraits model for the image viewer pane: the browsed folder,
its discovered images, the loaded pixel data, the display window, and the
slideshow state. Mutated only on the GUI thread (button events, timers,
the controller's loader), so no Qt bridging is needed.
"""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from traits.api import (
    Any,
    Bool,
    Button,
    Dict,
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
from traits.observation.api import parse

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import RangeWithViewHints

# Local imports.
from .analysis.roi_model import RoiAnalysisModel, roi_analysis_model
from .consts import (
    IMAGE_ZOOM_STEP_BOUNDS,
    IMAGE_ZOOM_STEP_DEFAULT,
    PERSISTED_VIEWER_TRAITS,
)
from .discovery import NO_IMAGE_GROUP, UNGROUPED_BURST, merge_image_groups
from .preferences import ImageViewerPreferences

#: The image filter's no-filter choice.
IMAGE_FILTER_ALL = "All"

#: The Image Group dropdown's every-group choice (the default).
IMAGE_GROUP_ALL = "All"

#: The capture-session dropdown's no-filter choice (spans every session).
BURST_FILTER_ALL = "All"


#: Ceiling of a 16-bit capture, the deepest frame the cameras
#: produce; the contrast window slides inside it.
UINT16_MAX = 65535.0

#: Default white point: raw fluorescence sits far below the 16-bit
#: ceiling, so opening at full range would show a black frame.
DEFAULT_WINDOW_MAX = 10000.0


class ImageViewerModel(HasTraits):
    """State for the captured-image viewer (16-bit aware)."""

    #: Folder being browsed. '' follows the current experiment's raw-captures
    #: folder; the folder button points it elsewhere.
    directory = Directory()

    #: The RESOLVED folder the last rescan looked at (the experiment's
    #: captures dir when ``directory`` is ''); display-only — drives the
    #: dock pane's "Name - folder" title.
    browsed_directory = Str()

    #: Section collapse toggles (controls-pane parity; not persisted).
    #: Experiments, Analysis Exclusion and Contrast start collapsed — the
    #: occasional affordances, not the everyday view.
    show_experiments = Bool(False)
    show_bursts = Bool(True)
    show_images = Bool(True)
    show_exclusion = Bool(False)
    show_contrast = Bool(False)

    #: The advanced-settings rows under the image (background ring,
    #: rolling ball, and the AI detection options) collapse under one
    #: "Advanced" chevron to reclaim vertical space.
    show_advanced_settings = Bool(True)

    #: One wheel notch's zoom factor on the image canvas (zooming out
    #: uses the reciprocal) — the Advanced group's sensitivity setting.
    zoom_step = Range(*IMAGE_ZOOM_STEP_BOUNDS, IMAGE_ZOOM_STEP_DEFAULT)

    #: Master toggle: the whole selector sidebar collapses to the left
    #: edge (device-viewer chevron parity).
    show_sidebar = Bool(True)

    #: Experiment folders that hold captures: ``[(name, captures_path), ...]``
    #: oldest first (discovery.discover_experiments). Selecting one repoints
    #: the viewer at that experiment's captures (``directory``).
    experiments = List()
    experiment_names = Property(List(Str), observe="experiments.items")
    selected_experiment = Str()
    experiment_index = Int(0)
    experiment_number = Property(Int, observe="experiment_index")
    max_experiment_number = Property(Int, observe="experiments.items")

    #: Discovered captures by Image Group (the type subfolder an image sits
    #: in): ``{image_group: [(session, [paths...]), ...]}``
    #: (discovery.discover_image_groups).
    image_groups = Dict()

    #: Image Group dropdown choices ("All", then "None", then the type
    #: subfolders) and its selection.
    image_group_names = Property(List(Str), observe="image_groups.items")
    selected_image_group = Str()

    #: The selected Image Group's Capture Sessions ("bursts"):
    #: ``[(burst_name, [paths...]), ...]``, oldest first. The VISIBLE image
    #: list below is the selected burst's paths through the image filter.
    bursts = List()

    #: Capture Session dropdown choices (mirrors ``bursts``) and its selection.
    burst_names = Property(List(Str), observe="bursts.items")
    selected_burst = Str()

    #: Burst seek-slider position within ``bursts``.
    burst_index = Int(0)
    max_burst_index = Property(Int, observe="bursts.items")

    #: The contributed filename filter (consts.IMAGE_FILTERS contract), or
    #: None when no plugin contributes one — the filter row then hides.
    image_filter = Any()

    #: The filter's dropdown label (its ``name``).
    filter_label = Property(Str, observe="image_filter")

    #: Filter choices: "All" plus every value the filter finds across the
    #: discovered files.
    filter_names = List(Str, value=[IMAGE_FILTER_ALL])
    selected_filter = Str(IMAGE_FILTER_ALL)

    #: Images shown for the current burst + filter (Path objects), oldest
    #: first. The dropdown / seek slider / position readout follow this.
    paths = List()

    #: Path of the displayed image ('' before the first load). Setting it
    #: is the ONE way an image gets shown — the controller loads it into
    #: ``array``.
    current_path = Str()

    #: Loaded pixel data (numpy uint16/uint8, gray or RGB), or None.
    array = Any()

    #: ``array`` perspective-warped and rolling-ball corrected while those
    #: corrections are on (``array`` itself otherwise), at its true values
    #: — what the canvas shows and the hover readout reads. Rendered off
    #: the GUI thread by the controller and set just before ``array``.
    corrected_array = Any()

    #: ``corrected_array`` windowed to 8-bit — the frame the canvas
    #: draws. Re-rendered off the GUI thread on every display-window or
    #: correction change.
    display_frame = Any()

    #: "name — WxH 16-bit gray" summary of the loaded image (shown in
    #: the dock pane's title).
    info_text = Str()

    #: "(x, y) = value" readout under the cursor (true stored values).
    pixel_text = Str()

    #: Scale readout for the status row ('' until a session loads).
    scale_text = Str()

    #: Basename choices for the image dropdown (mirrors ``paths``).
    image_names = Property(List(Str), observe="paths.items")

    #: Basename of the displayed image — the dropdown selection ('' when
    #: showing an image from outside the browsed folder).
    selected_image = Str()

    #: Seek-slider position within ``paths``.
    image_index = Int(0)
    max_image_index = Property(Int, observe="paths.items")

    #: 1-based twins of the seek indices — what the sliders BIND to, so
    #: the view counts 1..N while every internal index stays 0-based.
    image_number = Property(Int, observe="image_index")
    max_image_number = Property(Int, observe="paths.items")
    burst_number = Property(Int, observe="burst_index")
    max_burst_number = Property(Int, observe="bursts.items")

    # Display window: percentile auto-contrast, or the manual min/max pair.
    auto_contrast = Bool(
        True, desc="Window the displayed intensities to the 0.1–99.9 percentile range"
    )

    #:  Min/Max sliders — calibrates their scale (e.g. 4095 for 12-bit data).
    #: upper bound of the Min/Max sliders. Max - 1
    _max_window_min = Property(observe="window_max")

    window_min = RangeWithViewHints(
        0.0, "_max_window_min", 0.0, desc="intensity displayed as black"
    )
    window_max = RangeWithViewHints(
        1.0, UINT16_MAX, DEFAULT_WINDOW_MAX, desc="intensity displayed as white"
    )

    #: Slideshow auto-advance (the play/pause toggle).
    playing = Bool(False)

    #: One-shot request to refit the image to the pane.
    fit_request = Event()

    #: One-shot zoom request from the toolbar buttons: +1 zooms one step
    #: in, -1 one step out (the step is ``zoom_step``).
    zoom_request = Event()

    # Toolbar buttons (view events; the controller reacts).
    directory_button = Button()
    #: Back to the current experiment's raw-captures folder (newest image).
    home_button = Button()
    #: Show the displayed images' folder in the system file browser.
    open_folder_button = Button()
    fit_button = Button()
    zoom_in_button = Button()
    zoom_out_button = Button()
    previous_button = Button()
    next_button = Button()

    #: Persistence backing for the display window (two-way: edits push to
    #: preferences, external preference changes pull back) — the same
    #: pattern as the device status panes' persisted control values.
    preferences = Instance(ImageViewerPreferences, ImageViewerPreferences())

    #: ROI intensity-analysis state (shared with the plot pane).
    roi_analysis = Instance(RoiAnalysisModel)

    #: Guards the two-way preferences sync against echoing its own writes
    #: (declared trait, so the pull observer can read it in any ordering).
    _self_preference_change = Bool(False)

    #: "n/N" position across ALL the Image Group's images ("–/N" when
    #: showing an image from elsewhere, '' when nothing is discovered) — the
    #: arrows traverse the whole group, so the counter spans every session.
    position_text = Property(
        Str,
        observe=(
            "bursts.items, burst_index, selected_burst, "
            "selected_filter, paths.items, current_path"
        ),
    )

    def _roi_analysis_default(self):
        return roi_analysis_model

    def traits_init(self):
        self._self_preference_change = True
        self.trait_set(
            **{
                model_trait: getattr(self.preferences, preference_trait)
                for model_trait, preference_trait in PERSISTED_VIEWER_TRAITS.items()
            }
        )
        self._self_preference_change = False

    @observe(f"[{','.join(PERSISTED_VIEWER_TRAITS)}]", post_init=True)
    def _push_preferences(self, event):
        self._self_preference_change = True
        setattr(self.preferences, PERSISTED_VIEWER_TRAITS[event.name], event.new)
        self._self_preference_change = False

    @observe(
        parse("preferences").match(
            lambda name, trait: name in set(PERSISTED_VIEWER_TRAITS.values())
        )
    )
    def _pull_preferences(self, event):
        if self._self_preference_change:
            return
        for model_trait, preference_trait in PERSISTED_VIEWER_TRAITS.items():
            if preference_trait == event.name:
                self.trait_set(**{model_trait: event.new})

    def _get_image_names(self):
        return [path.name for path in self.paths]

    def _get_max_image_index(self):
        return max(len(self.paths) - 1, 0)

    def _get_burst_names(self):
        names = [name for name, _paths in self.bursts]
        return [BURST_FILTER_ALL] + names if names else []

    def _get_max_burst_index(self):
        return max(len(self.burst_names) - 1, 0)

    def _get_experiment_names(self):
        return [name for name, _captures in self.experiments]

    def _get_experiment_number(self):
        return self.experiment_index + 1

    def _set_experiment_number(self, value):
        self.experiment_index = value - 1

    def _get_max_experiment_number(self):
        return max(len(self.experiments), 1)

    def experiment_captures(self, name):
        """The named experiment's captures dir, or None for an unknown name."""
        for exp_name, captures in self.experiments:
            if exp_name == name:
                return captures
        return None

    def _get_image_number(self):
        return self.image_index + 1

    def _set_image_number(self, value):
        self.image_index = value - 1

    def _get_max_image_number(self):
        return max(len(self.paths), 1)

    def _get_burst_number(self):
        return self.burst_index + 1

    def _set_burst_number(self, value):
        self.burst_index = value - 1

    def _get_max_burst_number(self):
        return max(len(self.burst_names), 1)

    def _get_image_group_names(self):
        names = sorted(
            self.image_groups, key=lambda name: (name != NO_IMAGE_GROUP, name)
        )

        return [IMAGE_GROUP_ALL] + names if names else []

    def image_group_bursts(self, image_group):
        """The named Image Group's Capture Sessions — every group's images
        merged per session for "All"; [] for an unknown name."""
        if image_group == IMAGE_GROUP_ALL:
            return merge_image_groups(self.image_groups)

        return list(self.image_groups.get(image_group, []))

    def session_of(self, path):
        """The Capture Session ``path`` belongs to in the selected Image
        Group (``UNGROUPED_BURST`` when it is not in one)."""
        for name, paths in self.bursts:
            if Path(path) in paths:
                return name

        return UNGROUPED_BURST

    def burst_paths(self, burst_name):
        """The named burst's images — every group's, flattened in group
        order, for the "All" choice; [] for an unknown name."""
        if burst_name == BURST_FILTER_ALL:
            return [path for _name, paths in self.bursts for path in paths]
        for name, paths in self.bursts:
            if name == burst_name:
                return list(paths)
        return []

    def _get_filter_label(self):
        return self.image_filter.name if self.image_filter is not None else ""

    def filter_value(self, path):
        """The filter's value for ``path`` ('' with no filter or no match)."""
        if self.image_filter is None:
            return ""

        return self.image_filter.classify(path)

    def visible_of(self, paths):
        """``paths`` reduced by the active image filter (all when the
        filter is "All"). The single source of the filter rule — the
        controller's visible-list build and the group-wide position
        counter both go through it."""
        if self.selected_filter == IMAGE_FILTER_ALL:
            return list(paths)

        return [
            path for path in paths if self.filter_value(path) == self.selected_filter
        ]

    def _get_position_text(self):
        """Position across every capture session in the Image Group (the
        arrows traverse them all), through the active image filter — the
        images actually reachable. ``self.paths`` is already the filtered
        list; a specific group adds its predecessors' filtered counts,
        the "All" choice starts at zero."""
        total = sum(len(self.visible_of(paths)) for _name, paths in self.bursts)
        if total == 0:
            return ""
        before = 0
        if self.selected_burst != BURST_FILTER_ALL:
            for name, paths in self.bursts:
                if name == self.selected_burst:
                    break
                before += len(self.visible_of(paths))
        index = self.path_index()
        if index is not None:
            return f"{before + index + 1}/{total}"
        return f"–/{total}"

    def _get__max_window_min(self):
        return self.window_max - 1

    def path_index(self):
        """Index of the displayed image within ``paths``, or None when it
        came from elsewhere (or nothing is loaded)."""
        strings = [str(path) for path in self.paths]
        if self.current_path in strings:
            return strings.index(self.current_path)
        return None
