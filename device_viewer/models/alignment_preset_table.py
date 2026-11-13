# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state for the Camera Alignment window's Presets strip and its
naming dialog.

The table mirrors the store: one row per named preset, rebuilt whenever the
store changes. Renames and default changes made in the table are written
straight through (the window is modeless, so actions are immediate); Save
as, Apply and Delete need the live alignment or a confirmation and are
left to the owner through the buttons and ``apply_requested``."""

# Standard library imports.
from datetime import datetime

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Event,
    Float,
    HasTraits,
    Instance,
    List,
    Property,
    Str,
    Union,
    observe,
)

# Local imports.
from ..consts import (
    ALIGNMENT_PRESET_KIND_NAMED,
    ALIGNMENT_PRESET_SAVED_AT_FORMAT,
    PRESET_INVALID_FRAME_SIZE_NOTE,
    PRESET_OTHER_DEVICE_WARNING_TEMPLATE,
    PRESET_SHAPE_MISMATCH_NOTE,
)
from ..utils.alignment_geometry import same_aspect_ratio, valid_frame_size
from .alignment_preset import alignment_preset_name_error
from .alignment_preset_store import AlignmentPresetStore

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def local_saved_at_text(saved_at):
    """Return a UTC ISO 8601 save time as local time for the table, or the
    text unchanged when it does not parse."""
    try:
        return (
            datetime.fromisoformat(saved_at)
            .astimezone()
            .strftime(ALIGNMENT_PRESET_SAVED_AT_FORMAT)
        )
    except ValueError:
        return saved_at


def _sentence(note):
    """A status-bar note as a Warning-column sentence: capitalised."""
    return note[:1].upper() + note[1:]


class AlignmentPresetRow(HasTraits):
    """One saved preset in the table."""

    #: The preset's identity in the store; renames keep it.
    preset_id = Str()

    #: The preset's name, as edited in place (stripped when saved).
    name = Str()

    #: The name in the store, to tell a rename from no change.
    saved_name = Str()

    #: The device the preset was saved for.
    device_key = Str()

    #: When it was saved, in local time.
    saved_at_text = Str()

    #: Whether it is its device's default; one-hot per device, kept by the
    #: owning table.
    is_default = Bool()

    #: Whether it was saved for the loaded device.
    is_current_device = Bool()

    #: Whether Apply can put it on the loaded device.
    applicable = Bool()

    #: Whether it carries camera-side corners (not endpoint-only).
    has_camera_quad = Bool()

    #: The camera frame size it was saved at as [w, h]; None if unknown.
    frame_size = Union(None, List(Float))

    #: Paints the row in the active highlight: a loaded-device row while
    #: other devices' rows are listed too.
    highlighted = Bool()

    #: Why ``name`` cannot be used, or "".
    name_error = Str()

    #: What the Warning column shows: ``name_error``, else why the preset
    #: cannot be applied, else "".
    warning = Str()


class AlignmentPresetTable(HasTraits):
    """The Presets strip: the store's named presets as rows."""

    #: The presets library the rows mirror and write through to.
    store = Instance(AlignmentPresetStore)

    #: The loaded device's key; "" with none.
    current_device_key = Str()

    #: Whether the live alignment may change now — False while a protocol
    #: runs. Gates Apply.
    editable = Bool(True)

    #: List only the loaded device's presets.
    this_device_only = Bool(True)

    #: The camera's live frame size as [w, h]; None without a picture.
    #: A preset saved at another picture shape applies its endpoint only.
    live_frame_size = Union(None, List(Float))

    #: Whether the store accepts changes.
    writable = Property(Bool, observe="store.read_only")

    #: Why the store does not, shown above the table; "" while it does.
    notice = Property(Str, observe="store.read_only_reason")

    #: Whether Save as can run: the store writable and no protocol running.
    can_save = Property(Bool, observe="editable, writable")

    #: One row per listed preset: the loaded device's first, then by device
    #: and name.
    rows = List(Instance(AlignmentPresetRow))

    #: The row the table has selected.
    selected = Instance(AlignmentPresetRow)

    #: Whether Apply can run on the selected row.
    can_apply = Property(Bool, observe="selected.applicable, editable")

    #: Whether the selected row is its device's default — a top-level
    #: mirror, since enabled_when misses nested changes.
    selected_is_default = Property(Bool, observe="selected.is_default")

    #: Fires with the row to apply: from Apply, or a double-click outside
    #: the Name column (which edits the name instead).
    apply_requested = Event(Instance(AlignmentPresetRow))

    #: Set by the table editor to (row, column) on a double-click.
    double_clicked = Event()

    save_as_button = Button("Save as…")
    apply_button = Button("Apply")
    set_default_button = Button("Set Default")
    clear_default_button = Button("Clear Default")
    delete_button = Button("Delete")

    #: True while rows are rewritten from the store, so the write-through
    #: observers ignore the changes.
    _syncing = Bool(False)

    def _get_can_apply(self):
        return self.editable and self.selected is not None and self.selected.applicable

    def _get_selected_is_default(self):
        return self.selected is not None and self.selected.is_default

    def _get_writable(self):
        return self.store is not None and not self.store.read_only

    def _get_notice(self):
        return self.store.read_only_reason if self.store is not None else ""

    def _get_can_save(self):
        return self.editable and self.writable

    # ------------------------------------------------------------------ #
    @observe(
        "store.presets, store.defaults, current_device_key, this_device_only, "
        "live_frame_size"
    )
    def _rebuild_rows(self, event=None):
        """Mirror the store, reusing the row of every preset still listed so
        a rebuild during an in-place edit leaves the edited row alone."""

        if self.store is None:
            self.rows = []

            return

        current = self.current_device_key
        presets = sorted(
            (
                preset
                for preset in self.store.presets
                if preset.kind == ALIGNMENT_PRESET_KIND_NAMED
                and (not self.this_device_only or preset.device_key == current)
            ),
            key=lambda preset: (
                preset.device_key != current,
                preset.device_key.casefold(),
                preset.name.casefold(),
            ),
        )
        existing_rows = {row.preset_id: row for row in self.rows}
        rows = []

        self._syncing = True

        try:
            for preset in presets:
                row = existing_rows.get(preset.id) or AlignmentPresetRow(
                    preset_id=preset.id
                )
                row.trait_set(
                    saved_name=preset.name,
                    name=preset.name,
                    device_key=preset.device_key,
                    saved_at_text=local_saved_at_text(preset.saved_at),
                    is_default=self.store.is_default(preset.id),
                    has_camera_quad=not preset.is_endpoint_only,
                    frame_size=preset.frame_size,
                )
                rows.append(row)
        finally:
            self._syncing = False

        if [row.preset_id for row in rows] != [row.preset_id for row in self.rows]:
            selected = self.selected
            self.rows = rows

            # The table editor keeps its highlight on the old row index
            # through a reset; reselecting moves it back onto the row
            # that is actually selected.
            self.selected = None
            self.selected = selected if selected in rows else None

        self._update_row_states()

    @observe("rows:items:name")
    def _rename_in_store(self, event):
        row = event.object

        self._update_row_states()

        if self._syncing or row.name_error or row.name.strip() == row.saved_name:
            return

        try:
            self.store.rename(row.preset_id, row.name)
        except (OSError, ValueError) as exc:
            logger.error(f"Could not rename alignment preset '{row.saved_name}': {exc}")

            self._revert(row, name=row.saved_name)

    @observe("rows:items:is_default")
    def _keep_one_default_per_device(self, event):
        if self._syncing:
            return

        row = event.object

        if row.is_default:
            self._revert(
                *(
                    other
                    for other in self.rows
                    if other is not row and other.device_key == row.device_key
                ),
                is_default=False,
            )

        if self.store is None:
            return

        try:
            if row.is_default:
                self.store.set_default(row.preset_id)
            else:
                self.store.clear_default(row.device_key)
        except (OSError, ValueError) as exc:
            logger.error(f"Could not change the default alignment preset: {exc}")

            # The rebuild puts every row back on the store's defaults.
            self._rebuild_rows()

    @observe("set_default_button")
    def _make_selected_default(self, event):
        if self.selected is not None:
            self.selected.is_default = True

    @observe("clear_default_button")
    def _clear_selected_default(self, event):
        if self.selected is not None:
            self.selected.is_default = False

    @observe("apply_button")
    def _apply_selected(self, event):
        if self.can_apply:
            self.apply_requested = self.selected

    @observe("double_clicked")
    def _apply_double_clicked(self, event):
        row, column = event.new

        # A double-click on the name edits it in place instead.
        if column.name == "name":
            return

        self.selected = row

        if self.can_apply:
            self.apply_requested = row

    # ------------------------------------------------------------------ #
    def _revert(self, *rows, **traits):
        """Set ``traits`` on ``rows`` without writing them to the store."""
        self._syncing = True

        try:
            for row in rows:
                row.trait_set(**traits)
        finally:
            self._syncing = False

        self._update_row_states()

    def _update_row_states(self):
        for row in self.rows:
            row.is_current_device = row.device_key == self.current_device_key
            row.applicable = row.is_current_device
            row.highlighted = row.is_current_device and not self.this_device_only
            row.name_error = self._name_error_for(row)
            row.warning = row.name_error or self._applicability_warning_for(row)

    def _name_error_for(self, row):
        if self.store is None:
            return alignment_preset_name_error(row.name)

        return self.store.name_error(row.name, row.device_key, row.preset_id)

    def _applicability_warning_for(self, row):
        """Why Apply cannot put ``row`` (fully) on the live alignment, or ""."""

        if not row.applicable:
            return PRESET_OTHER_DEVICE_WARNING_TEMPLATE.format(
                device_key=row.device_key
            )

        if not row.has_camera_quad or row.frame_size is None:
            return ""

        if not valid_frame_size(row.frame_size):
            return _sentence(PRESET_INVALID_FRAME_SIZE_NOTE)

        live_frame_size = self.live_frame_size

        if valid_frame_size(live_frame_size) and not same_aspect_ratio(
            row.frame_size, live_frame_size
        ):
            return _sentence(PRESET_SHAPE_MISMATCH_NOTE)

        return ""


class AlignmentPresetName(HasTraits):
    """Qt-free state for the Save Alignment Preset naming dialog."""

    #: The name to save the preset under, as typed (stripped on save).
    name = Str()

    #: Why ``name`` cannot be used, or "" when it can. A name the device
    #: already uses is allowed here: saving then asks to replace it.
    name_error = Property(Str, observe="name")

    #: Whether ``name`` can be used — gates the dialog's OK button.
    is_name_valid = Property(Bool, observe="name")

    #: The device the preset is saved for (shown, not edited).
    device_key = Str()

    #: What the preset will hold, e.g. that it is endpoint-only.
    note = Str()

    #: Make the saved preset its device's default.
    make_default = Bool(False)

    def _get_name_error(self):
        return alignment_preset_name_error(self.name)

    def _get_is_name_valid(self):
        return not self.name_error
