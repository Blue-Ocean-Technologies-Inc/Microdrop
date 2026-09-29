# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

# The viewer reads capture files straight off disk; it subscribes to no
# topics.
ACTOR_TOPIC_DICT = {}

# ---------------------------------------------------------------------------
# Extension point: filename-derived filters for the image list (e.g. the
# fluorescence plugin's LED-wavelength filter). Contributions are objects
# with:
#   name: str                 # dropdown label and the ROI CSV column name
#   tooltip: str              # dropdown tooltip
#   classify(path) -> str     # the path's value, '' when it has none
# The first contribution drives the filter dropdown; with none contributed
# the dropdown is hidden. Resolved on every rescan, so a hot-loaded plugin's
# filter appears without reopening the pane.
# ---------------------------------------------------------------------------
IMAGE_FILTERS = f"{PKG}.image_filters"

#: Preferences node for the viewer's own settings.
PREFERENCES_PATH = "microdrop.image_viewer"

#: Settings the viewer inherited from the fluorescence plugin, which kept
#: them on the shared Peripheral Settings node: ImageViewerPreferences trait
#: -> legacy key. Copied over once so saved fit presets and calibrations
#: survive the move.
LEGACY_PREFERENCE_KEYS = {
    "last_scale_metres_per_px": (
        "microdrop.peripheral_settings.fluorescence_last_scale_metres_per_px"
    ),
    "last_scale_unit": "microdrop.peripheral_settings.fluorescence_last_scale_unit",
    "fit_presets": "microdrop.peripheral_settings.fluorescence_fit_presets",
    "ai_use_gpu": "microdrop.peripheral_settings.fluorescence_ai_use_gpu",
    "ai_model": "microdrop.peripheral_settings.fluorescence_ai_model",
    "auto_contrast": (
        "microdrop.peripheral_settings.fluorescence_viewer_auto_contrast"
    ),
    "window_min": "microdrop.peripheral_settings.fluorescence_viewer_window_min",
    "window_max": "microdrop.peripheral_settings.fluorescence_viewer_window_max",
}

# Display-window values persisted across sessions: model trait ->
# ImageViewerPreferences trait. window_max restores BEFORE window_min:
# window_min's upper bound rides window_max, so the reverse order could
# reject a stored min above the not-yet-restored max.
PERSISTED_VIEWER_TRAITS = {
    "auto_contrast": "auto_contrast",
    "window_max": "window_max",
    "window_min": "window_min",
}

#: Filename patterns counted as viewable images when browsing a folder.
IMAGE_PATTERNS = ("*.png", "*.tif", "*.tiff", "*.jpg", "*.jpeg", "*.bmp")
#: Rescan cadence for newly landed captures / experiment switches (ms).
DISCOVERY_POLL_INTERVAL_MS = 2_000
#: Auto-advance cadence while the slideshow is playing (ms).
SLIDESHOW_INTERVAL_MS = 1_500

#: strftime format of the UTC stamp embedded in capture filenames
#: (discovery.utc_stamp writes it; discovery.capture_timestamp parses it
#: back).
CAPTURE_TIMESTAMP_FORMAT = "%Y_%m_%d-%H_%M_%S"

#: Decoded frames kept in the viewer's navigation cache. Full 16-bit
#: frames run ~20 MB decoded, so this bounds the cache near 160 MB while
#: making back-and-forth seeking over recent frames instant.
IMAGE_CACHE_FRAMES = 8

#: One wheel notch's zoom on the image canvas: default factor going in
#: (going out is its reciprocal) and the range the Advanced setting
#: allows. 1.05 is barely perceptible per notch; 2.0 doubles per notch.
IMAGE_ZOOM_STEP_DEFAULT = 1.25
IMAGE_ZOOM_STEP_BOUNDS = (1.05, 2.0)
