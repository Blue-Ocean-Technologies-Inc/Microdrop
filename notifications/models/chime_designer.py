# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The chime designer's choices, Qt-free: how the notification tones sound.

A base design (timbre, melody, pitch shift, room echo, ring length) applies
to every tone; any tone may instead have its own design, an override, a
complete design of its own that no longer follows the base. The designer
edits one at a time through a single set of fields: the base while "All
tones" is chosen, else that tone's override, made from the base on its
first edit. "Use the base" drops the chosen tone's override; "Reset to
default" restores the default base and drops every override.

The default base with no overrides is the shipped set of WAVs. Saved as
``{"base": {...}, "overrides": {tone: {...}}}`` within the notification
settings (``to_state``/``apply_state``).
"""

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Dict,
    Enum,
    Event,
    HasTraits,
    Instance,
    Range,
    Str,
    TraitError,
    observe,
)

# Microdrop style imports.
from microdrop_style.sounds.chime_synth import (
    DEFAULT_DESIGN,
    DEFAULT_PITCH_SHIFT,
    DEFAULT_RING_LENGTH,
    DEFAULT_ROOM,
    MELODIES,
    PITCH_SHIFT_RANGE,
    RING_LENGTH_RANGE,
    ROOM_RANGE,
    TIMBRES,
)

# Local imports.
from ..consts import (
    TONE_ALERT,
    TONE_COMPLETION,
    TONE_CONNECTED,
    TONE_DISCONNECTED,
    TONE_LABELS,
    TONE_NONE,
    TONE_SOFT,
    TONES,
)

#: The tones a design can be made for: every one that sounds.
SOUNDING_TONES = tuple(tone for tone in TONES if tone != TONE_NONE)

#: The designer's choice meaning the base, for every tone.
ALL_TONES = "all"

#: A design's fields, as saved and as the designer edits them.
DESIGN_FIELDS = tuple(DEFAULT_DESIGN)

#: The keys of the base and the overrides in the saved dict.
BASE_KEY = "base"
OVERRIDES_KEY = "overrides"


class ChimeDesign(HasTraits):
    """How a tone sounds: its timbre, its melody's figure, and the shift,
    room echo and ring length applied to it."""

    #: The struck note's sound, by ``chime_synth.TIMBRES`` key.
    timbre = Enum(*TIMBRES)

    #: The melody scheme whose figure the tone plays, by
    #: ``chime_synth.MELODIES`` key.
    melody = Enum(*MELODIES)

    #: Semitones up or down from the melody's pitches.
    pitch_shift = Range(*PITCH_SHIFT_RANGE, value=DEFAULT_PITCH_SHIFT)

    #: The room echo's level and the notes' ring, as % of the usual.
    room = Range(*ROOM_RANGE, value=DEFAULT_ROOM)
    ring_length = Range(*RING_LENGTH_RANGE, value=DEFAULT_RING_LENGTH)

    def to_state(self):
        """The design as a JSON-ready dict, ``chime_synth``'s keywords."""
        return {name: getattr(self, name) for name in DESIGN_FIELDS}

    def is_default(self):
        """Whether this is the design the shipped chimes stand for."""
        return self.to_state() == DEFAULT_DESIGN


def design_from_state(state):
    """A design from ``to_state``'s dict, or None if any value is unusable;
    a missing field keeps its default."""

    if not isinstance(state, dict):
        return None

    values = {name: state[name] for name in DESIGN_FIELDS if name in state}

    try:
        return ChimeDesign(**values)

    except TraitError:
        return None


class ChimeDesigner(HasTraits):
    """The base design, the tones' overrides, and the fields editing one
    of them."""

    #: The design every tone without an override follows.
    base = Instance(ChimeDesign, ())

    #: Each overridden tone's own design, by tone.
    overrides = Dict(Str, Instance(ChimeDesign))

    #: Fired whenever any tone's design changes: the chime re-renders and
    #: the settings are saved.
    updated = Event()

    #: Fired with a tone to hear it as designed.
    preview = Event()

    #: What the fields edit: ALL_TONES for the base, else a tone.
    editing_tone = Enum(ALL_TONES, *SOUNDING_TONES)

    #: The fields, showing and editing the design ``editing_tone`` picks.
    timbre = Enum(*TIMBRES)
    melody = Enum(*MELODIES)
    pitch_shift = Range(*PITCH_SHIFT_RANGE, value=DEFAULT_PITCH_SHIFT)
    room = Range(*ROOM_RANGE, value=DEFAULT_ROOM)
    ring_length = Range(*RING_LENGTH_RANGE, value=DEFAULT_RING_LENGTH)

    #: Whether the edited tone has its own design (for ``enabled_when``).
    has_override = Bool(False)

    #: Says what the fields edit, and which tones have their own design.
    editing_summary = Str()

    #: Drops the edited tone's override; restores the whole default set.
    use_base = Button("Use the base")
    reset_to_default = Button("Reset to default")

    #: A preview button per tone.
    play_soft = Button(TONE_LABELS[TONE_SOFT])
    play_connected = Button(TONE_LABELS[TONE_CONNECTED])
    play_disconnected = Button(TONE_LABELS[TONE_DISCONNECTED])
    play_alert = Button(TONE_LABELS[TONE_ALERT])
    play_completion = Button(TONE_LABELS[TONE_COMPLETION])

    #: Set while the fields are being shown, so showing is not editing.
    _showing = Bool(False)

    def traits_init(self):
        self._show_edited_design()

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def design(self, tone):
        """The design ``tone`` sounds with: its override, else the base."""
        return self.overrides.get(tone, self.base)

    def is_default(self):
        """Whether every tone sounds as shipped."""
        return all(self.design(tone).is_default() for tone in SOUNDING_TONES)

    def reset(self):
        """The default base, and no overrides."""
        self.base = ChimeDesign()
        self.overrides = {}
        self._changed()

    def to_state(self):
        """The designs as a JSON-ready dict, for ``apply_state``."""
        return {
            BASE_KEY: self.base.to_state(),
            OVERRIDES_KEY: {
                tone: design.to_state() for tone, design in self.overrides.items()
            },
        }

    def apply_state(self, state):
        """Take the designs in ``state`` (``to_state``'s dict); what it lacks
        keeps its default. Returns the keys whose values were unusable, which
        are ignored."""
        rejected = []
        base = design_from_state(state.get(BASE_KEY, {}))

        if base is None:
            rejected.append(BASE_KEY)
            base = ChimeDesign()

        overrides = {}
        saved_overrides = state.get(OVERRIDES_KEY, {})

        if not isinstance(saved_overrides, dict):
            rejected.append(OVERRIDES_KEY)
            saved_overrides = {}

        for tone, saved in saved_overrides.items():
            design = design_from_state(saved) if tone in SOUNDING_TONES else None

            if design is None:
                rejected.append(f"{OVERRIDES_KEY}.{tone}")

                continue

            overrides[tone] = design

        self.base = base
        self.overrides = overrides
        self._changed()

        return rejected

    # ------------------------------------------------------------------ #
    # Editing                                                             #
    # ------------------------------------------------------------------ #

    @observe("editing_tone")
    def _edit_another(self, event):
        self._show_edited_design()

    @observe("timbre, melody, pitch_shift, room, ring_length")
    def _edit(self, event):

        if self._showing:
            return

        tone = self.editing_tone

        if tone == ALL_TONES:
            target = self.base

        else:
            target = self.overrides.get(tone)

            if target is None:
                target = ChimeDesign(**self.base.to_state())
                self.overrides = {**self.overrides, tone: target}

        setattr(target, event.name, event.new)
        self._changed()

    @observe("use_base")
    def _drop_override(self, event):
        overrides = dict(self.overrides)

        overrides.pop(self.editing_tone, None)
        self.overrides = overrides
        self._changed()

    @observe("reset_to_default")
    def _reset(self, event):
        self.reset()

    @observe("play_soft, play_connected, play_disconnected, play_alert")
    @observe("play_completion")
    def _play(self, event):
        self.preview = event.name.removeprefix("play_")

    def _changed(self):
        self._show_edited_design()
        self.updated = True

    def _show_edited_design(self):
        """The fields, override flag and summary for ``editing_tone``."""
        tone = self.editing_tone
        design = self.base if tone == ALL_TONES else self.design(tone)
        own = [TONE_LABELS[tone] for tone in SOUNDING_TONES if tone in self.overrides]

        self._showing = True

        try:
            self.trait_set(**design.to_state())

        finally:
            self._showing = False

        self.has_override = tone in self.overrides

        if tone == ALL_TONES:
            following = "every tone" if not own else f"all but {', '.join(own)}"
            self.editing_summary = f"Editing the base, for {following}"

        elif self.has_override:
            self.editing_summary = f"Editing {TONE_LABELS[tone]}'s own sound"

        else:
            self.editing_summary = (
                f"{TONE_LABELS[tone]} follows the base; a change gives it its own"
            )
