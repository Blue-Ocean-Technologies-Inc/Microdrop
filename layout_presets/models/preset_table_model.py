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
preset, renames, shortcut edits and deletions staged until the dialog is
accepted."""

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Dict,
    HasTraits,
    Instance,
    List,
    Property,
    Str,
    observe,
)

# Local imports.
from .preset_name_model import preset_shortcut_owner, shortcut_collision_warning
from .preset_store import preset_name_error


class PresetRow(HasTraits):
    """One saved preset in the table."""

    #: The preset's name, as edited (stripped when applied).
    name = Str()

    #: The name saved on disk, to tell a rename from no change.
    saved_name = Str()

    #: Key sequence (Qt portable text) applying the preset; "" for none.
    shortcut = Str()

    #: The shortcut saved on disk, to tell an edit from no change.
    saved_shortcut = Str()

    #: Why ``name`` cannot be used, or ""; blocks accepting the dialog.
    #: Kept by the owning table.
    name_error = Str()

    #: What the row's Warning column shows: ``name_error``, else what
    #: ``shortcut`` collides with, else "". Kept by the owning table.
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

    #: Every preset file on disk, readable or not — a rename may not take
    #: one of these names unless its row is staged for deletion.
    disk_names = List(Str)

    #: Whether every row's name can be applied — gates the OK button.
    can_accept = Property(Bool, observe="rows.items.name_error")

    #: Stages the selected row's deletion.
    delete_button = Button("Delete Preset")

    @classmethod
    def from_store(cls, store, used_shortcuts):
        """Return a table over ``store``'s presets."""
        rows = [
            PresetRow(
                name=name,
                saved_name=name,
                shortcut=store.shortcut_for(name),
                saved_shortcut=store.shortcut_for(name),
            )
            for name in store.presets
        ]

        return cls(
            rows=rows, used_shortcuts=used_shortcuts, disk_names=store.saved_names()
        )

    def delete_selected(self):
        """Stage the selected row's deletion."""
        if self.selected is not None:
            self.rows.remove(self.selected)
            self.selected = None

    def changes(self):
        """Return ``(deleted names, {old name: new name}, {name: new
        shortcut})`` to apply in that order; shortcuts use the new names."""
        renamed = {
            row.saved_name: row.name.strip()
            for row in self.rows
            if row.name.strip() != row.saved_name
        }
        changed_shortcuts = {
            row.name.strip(): row.shortcut
            for row in self.rows
            if row.shortcut != row.saved_shortcut
        }

        return list(self.deleted_names), renamed, changed_shortcuts

    def _get_can_accept(self):
        return not any(row.name_error for row in self.rows)

    @observe("delete_button")
    def _delete_selected_row(self, event):
        self.delete_selected()

    @observe("rows:items")
    def _track_deleted_rows(self, event):
        self.deleted_names.extend(row.saved_name for row in event.removed)

    @observe(
        [
            "rows.items.name",
            "rows.items.shortcut",
            "used_shortcuts",
            "deleted_names.items",
            "disk_names.items",
        ]
    )
    def _update_warnings(self, event):
        for row in self.rows:
            row.name_error = self._name_error_for(row)
            row.warning = row.name_error or self._shortcut_warning_for(row)

    def _name_error_for(self, row):
        """Return why ``row``'s name cannot be applied, or ""."""
        error = preset_name_error(row.name)

        if error:
            return error

        name = row.name.strip().casefold()

        # Another row's current or saved name is taken (its file is still on
        # disk while renames apply); so is any other preset file, unless
        # its row is staged for deletion, which is applied first.
        taken_names = {
            taken.casefold()
            for other in self.rows
            if other is not row
            for taken in (other.name.strip(), other.saved_name)
        }
        freed_names = {deleted.casefold() for deleted in self.deleted_names}
        taken_names |= {
            disk_name.casefold()
            for disk_name in self.disk_names
            if disk_name.casefold() != row.saved_name.casefold()
        } - freed_names

        if name in taken_names:
            return f"Another preset is already named '{row.name.strip()}'."

        return ""

    def _shortcut_warning_for(self, row):
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
