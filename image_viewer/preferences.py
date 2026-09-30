# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Image viewer preferences: the display window, the last scale
calibration, saved fit equations, and the AI ROI detection options."""

# Enthought library imports.
from apptools.preferences.api import PreferencesHelper
from envisage.ui.tasks.api import PreferencesCategory, PreferencesPane
from traits.api import Bool, Float, Str
from traitsui.api import EnumEditor, Item, VGroup, View

# Microdrop style imports.
from microdrop_style.text_styles import preferences_group_style_sheet

# Microdrop utils imports.
from microdrop_utils.preferences_UI_helpers import create_item_label_group

# Local imports.
from .analysis.sam_detect import AI_MODEL_OPTIONS, DEFAULT_AI_MODEL
from .consts import LEGACY_PREFERENCE_KEYS, PREFERENCES_PATH
from .scale_bar import DEFAULT_UNIT

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class ImageViewerPreferences(PreferencesHelper):
    """The image viewer's own preferences node."""

    preferences_path = Str(PREFERENCES_PATH)

    # Last scale calibration, used to seed an experiment that has none
    # (the seeded value is written into that experiment on first use).
    last_scale_metres_per_px = Float(
        0.0, desc="Metres per image pixel from the last calibration"
    )
    last_scale_unit = Str(DEFAULT_UNIT, desc="Unit the last calibration was entered in")

    # The user's saved fit equations, as JSON [{name, expression}, ...].
    # App-wide: an equation re-typed per experiment is not a preset.
    fit_presets = Str("", desc="Saved custom fit equations (JSON)")

    # SAM model for AI ROI detection. Weights are downloaded on demand
    # (cancellable dialog); cancel reverts this. The DirectML (GPU)
    # onnxruntime build encodes ~3x faster but is not installed (it clashes
    # with osam's CPU build); without it the encoder stays on CPU.
    ai_use_gpu = Bool(
        True, desc="Run the SAM encoder on the GPU (DirectML) when available"
    )
    ai_model = Str(DEFAULT_AI_MODEL, desc="SAM model for AI ROI detection")

    # Display window. Edited from the viewer pane's own toolbar —
    # deliberately NOT on the preferences tab.
    auto_contrast = Bool(True, desc="Auto-contrast the image viewer display window")
    window_min = Float(
        0, desc="Manual display-window minimum (used when auto-contrast is off)"
    )
    window_max = Float(
        10000, desc="Manual display-window maximum (used when auto-contrast is off)"
    )


def migrate_legacy_preferences(preferences):
    """Copy the settings the fluorescence plugin used to own into this
    node, once: only keys the new node has never stored are filled, so
    later edits are never overwritten."""
    migrated = []

    for trait_name, legacy_key in LEGACY_PREFERENCE_KEYS.items():
        key = f"{PREFERENCES_PATH}.{trait_name}"
        legacy_value = preferences.get(legacy_key)

        if legacy_value is not None and preferences.get(key) is None:
            preferences.set(key, legacy_value)
            migrated.append(trait_name)

    if migrated:
        preferences.flush()
        logger.info(f"Migrated image viewer preferences: {', '.join(migrated)}")


image_viewer_tab = PreferencesCategory(
    id=f"{PREFERENCES_PATH}.preferences",
    name="Image Viewer",
)


class ImageViewerPreferencesPane(PreferencesPane):
    """The Image Viewer preferences tab."""

    model_factory = ImageViewerPreferences

    category = image_viewer_tab.id

    # EnumEditor's dict `values` sorts by the displayed string, so the
    # display label is prefixed with its AI_MODEL_OPTIONS index (shown
    # after the colon by the editor) to keep speed/accuracy pairs in
    # their declared order rather than alphabetical.
    ai_group = VGroup(
        create_item_label_group(
            "ai_model",
            label_text="AI ROI detection model",
            editor=EnumEditor(
                values={
                    name: f"{index}:{label}"
                    for index, (name, label) in enumerate(AI_MODEL_OPTIONS)
                }
            ),
        ),
        create_item_label_group(
            "ai_use_gpu",
            label_text="Run the SAM encoder on the GPU (DirectML)",
        ),
        label="AI ROI Detection",
        show_border=True,
        style_sheet=preferences_group_style_sheet,
    )

    view = View(
        ai_group,
        Item("_"),  # Separator to space this out from further contributions.
        resizable=True,
    )
