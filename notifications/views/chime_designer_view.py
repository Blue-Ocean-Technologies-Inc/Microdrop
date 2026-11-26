# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The chime designer's view: which tone the fields edit, the fields, and a
preview button per tone. Shown in the notification settings' Sounds tab, or
standalone against just the model::

    ChimeDesigner().edit_traits(view=CHIME_DESIGNER_VIEW)
"""

# Enthought library imports.
from traitsui.api import EnumEditor, HGroup, Item, RangeEditor, VGroup, View

# Microdrop style imports.
from microdrop_style.sounds.chime_synth import (
    MELODY_LABELS,
    PITCH_SHIFT_RANGE,
    RING_LENGTH_RANGE,
    ROOM_RANGE,
    TIMBRE_LABELS,
)

# Local imports.
from ..consts import TONE_LABELS
from ..models.chime_designer import ALL_TONES, SOUNDING_TONES


def _ordered_choices(labels):
    """``labels`` (by key) in their order, as EnumEditor wants them."""
    return {
        key: f"{index}:{label}" for index, (key, label) in enumerate(labels.items())
    }


#: What the fields can edit: the base, or one tone's own design.
EDITING_CHOICES = _ordered_choices(
    {ALL_TONES: "All tones", **{tone: TONE_LABELS[tone] for tone in SOUNDING_TONES}}
)

CHIME_DESIGNER_VIEW = View(
    VGroup(
        Item(
            "editing_tone",
            label="Edit",
            editor=EnumEditor(values=EDITING_CHOICES),
            tooltip=(
                "All tones edits the base every tone follows; a single tone "
                "gets its own sound on its first change"
            ),
        ),
        Item("editing_summary", show_label=False, style="readonly"),
        Item("timbre", editor=EnumEditor(values=_ordered_choices(TIMBRE_LABELS))),
        Item(
            "melody",
            editor=EnumEditor(values=_ordered_choices(MELODY_LABELS)),
            tooltip="The scheme giving each tone its own figure of notes",
        ),
        Item(
            "pitch_shift",
            label="Pitch shift (semitones)",
            editor=RangeEditor(
                low=PITCH_SHIFT_RANGE[0], high=PITCH_SHIFT_RANGE[1], mode="spinner"
            ),
        ),
        Item(
            "room",
            label="Room echo (%)",
            editor=RangeEditor(low=ROOM_RANGE[0], high=ROOM_RANGE[1], mode="slider"),
        ),
        Item(
            "ring_length",
            label="Ring length (%)",
            editor=RangeEditor(
                low=RING_LENGTH_RANGE[0], high=RING_LENGTH_RANGE[1], mode="slider"
            ),
        ),
        HGroup(
            Item(
                "use_base",
                enabled_when="has_override",
                tooltip="This tone follows the base again",
            ),
            Item(
                "reset_to_default",
                tooltip="The default sounds for every tone",
            ),
            show_labels=False,
        ),
        HGroup(
            Item("play_soft"),
            Item("play_connected"),
            Item("play_disconnected"),
            Item("play_alert"),
            Item("play_completion"),
            label="Preview, at the chosen volume",
            show_labels=False,
            show_border=True,
        ),
    ),
    title="Chime designer",
    resizable=True,
)
