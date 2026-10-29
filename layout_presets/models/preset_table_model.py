# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state for the Manage Layout Presets dialog: one row per saved
preset, edits and deletions staged until the dialog is accepted."""

# Enthought library imports.
from traits.api import Button, Dict, HasTraits, Instance, List, Str, observe

# Local imports.
from .preset_name_model import preset_shortcut_owner, shortcut_collision_warning


class PresetRow(HasTraits):
    """One saved preset in the table."""

    #: The preset's name; read-only in the table.
    name = Str()

    #: Key sequence (Qt portable text) applying the preset; "" for none.
    shortcut = Str()

    #: The shortcut saved on disk, to tell an edit from no change.
    saved_shortcut = Str()

    #: What ``shortcut`` collides with, or ""; kept by the owning table.
    warning = Str()


class PresetTable(HasTraits):
    """The presets being managed, with the user's staged changes."""

    #: One row per preset not (yet) deleted, in menu order.
    rows = List(Instance(PresetRow))

    #: The row the table has selected.
    selected = Instance(PresetRow)

    #: Key sequence -> what outside the presets already uses it.
    used_shortcuts = Dict(Str, Str)

    #: Names of the rows the user deleted, in deletion order.
    deleted_names = List(Str)

    #: Stages the selected row's deletion.
    delete_button = Button("Delete Preset")

    @classmethod
    def from_store(cls, store, used_shortcuts):
        """Return a table over ``store``'s presets."""
        rows = [
            PresetRow(
                name=name,
                shortcut=store.shortcut_for(name),
                saved_shortcut=store.shortcut_for(name),
            )
            for name in store.presets
        ]

        return cls(rows=rows, used_shortcuts=used_shortcuts)

    def delete_selected(self):
        """Stage the selected row's deletion."""
        if self.selected is not None:
            self.rows.remove(self.selected)
            self.selected = None

    def changes(self):
        """Return ``(deleted names, {name: new shortcut})`` to apply."""
        changed_shortcuts = {
            row.name: row.shortcut
            for row in self.rows
            if row.shortcut != row.saved_shortcut
        }

        return list(self.deleted_names), changed_shortcuts

    @observe("delete_button")
    def _delete_selected_row(self, event):
        self.delete_selected()

    @observe("rows:items")
    def _track_deleted_rows(self, event):
        self.deleted_names.extend(row.name for row in event.removed)

    @observe(["rows.items.shortcut", "used_shortcuts"])
    def _update_warnings(self, event):
        for row in self.rows:
            row.warning = self._warning_for(row)

    def _warning_for(self, row):
        """Return what ``row``'s shortcut collides with, or ""."""
        if not row.shortcut:
            return ""

        owner = self.used_shortcuts.get(row.shortcut, "")

        if owner:
            return shortcut_collision_warning(row.shortcut, owner)

        # Two rows on one chord warn each other.
        for other in self.rows:
            if other is not row and other.shortcut == row.shortcut:
                return shortcut_collision_warning(
                    row.shortcut, preset_shortcut_owner(other.name)
                )

        return ""
