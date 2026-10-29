# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from traits.api import Bool, Dict, HasTraits, Property, Str

# Local imports.
from .preset_store import preset_name_error


def preset_shortcut_owner(name):
    """Return how a preset is named as the user of a shortcut."""
    return f"preset '{name.strip()}'"


class PresetName(HasTraits):
    """Qt-free state for the Save Current Layout naming dialog."""

    #: The name to save the preset under, as typed (stripped on save).
    name = Str()

    #: Why ``name`` cannot be used, or "" when it can.
    name_error = Property(Str, observe="name")

    #: Whether ``name`` can be used — gates the dialog's OK button.
    is_name_valid = Property(Bool, observe="name")

    #: Key sequence (Qt portable text) applying the preset; "" for none.
    shortcut = Str()

    #: Key sequence (same text form) -> what already uses it, e.g.
    #: "Reset Layout" or "preset 'wide'".
    used_shortcuts = Dict(Str, Str)

    #: What ``shortcut`` collides with, or "". Informational only: saving
    #: stays allowed.
    shortcut_warning = Property(Str, observe=["shortcut", "used_shortcuts", "name"])

    def _get_name_error(self):
        return preset_name_error(self.name)

    def _get_is_name_valid(self):
        return not self.name_error

    def _get_shortcut_warning(self):
        owner = self.used_shortcuts.get(self.shortcut, "")

        # The preset being overwritten gives its shortcut up, so reusing it
        # is no collision.
        if not self.shortcut or owner in ("", preset_shortcut_owner(self.name)):
            return ""

        return f"{self.shortcut} is already used by {owner}"
