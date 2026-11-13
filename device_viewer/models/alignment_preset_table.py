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
store, the selected camera or the loaded device changes. Renames, scope and
default changes made in the table are written straight through (the window
is modeless, so actions are immediate); Save as, Apply and Delete need the
live alignment or a confirmation and are left to the owner through the
buttons and ``apply_requested``."""

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
    ALIGNMENT_PRESET_SCOPE_CAMERA,
    ALIGNMENT_PRESET_SCOPE_DEVICE,
    ALIGNMENT_PRESET_SCOPE_LABELS,
    ALIGNMENT_SETUP_TEMPLATE,
    ANY_CAMERA_TEXT,
    ANY_CAMERA_TOOLTIP_TEMPLATE,
    CAMERA_ID_TOOLTIP_TEMPLATE,
    CAMERA_WITHOUT_ID_TOOLTIP,
    NO_CAMERA_TEXT,
    NO_DEFAULT_PRESET_TEXT,
    PRESET_DEVICE_SIZE_UNKNOWN_NOTE,
    PRESET_INVALID_FRAME_SIZE_NOTE,
    PRESET_OTHER_CAMERA_WARNING_TEMPLATE,
    PRESET_OTHER_DEVICE_WARNING_TEMPLATE,
    PRESET_SHAPE_MISMATCH_NOTE,
    SCOPE_CHANGE_FAILED_TEMPLATE,
)
from ..utils.alignment_geometry import (
    quad_between_scene_rects,
    same_aspect_ratio,
    valid_frame_size,
)
from .alignment_preset import alignment_preset_name_error, alignment_scope_error
from .alignment_preset_store import AlignmentPresetStore
from .camera_identity import CameraIdentity

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


def scope_code(scope_label):
    """The scope a label of ALIGNMENT_PRESET_SCOPE_LABELS reads as."""
    return next(
        code
        for code, label in ALIGNMENT_PRESET_SCOPE_LABELS.items()
        if label == scope_label
    )


def scope_labels_for(camera_label, camera_id, has_camera_quad):
    """The scope labels a preset saved with this camera (and camera
    corners or not) can have, in display order."""
    return [
        label
        for code, label in ALIGNMENT_PRESET_SCOPE_LABELS.items()
        if not alignment_scope_error(code, camera_label, camera_id, has_camera_quad)
    ]


def _sentence(note):
    """A status-bar note as a Warning-column sentence: capitalised."""
    return note[:1].upper() + note[1:]


def _quoted(camera):
    return f"'{camera.display_text}'"


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

    #: The preset's scope (an ALIGNMENT_PRESET_SCOPE_* value).
    scope = Str(ALIGNMENT_PRESET_SCOPE_DEVICE)

    #: The scope as the Scope column reads it.
    scope_text = Str()

    #: The scope labels this preset can take (its camera and geometry
    #: decide).
    scope_choices = List(Str)

    #: The camera it was saved with.
    camera = Instance(CameraIdentity, ())

    #: The Camera column: the camera's label, or "Any camera" for a
    #: device-scoped preset.
    camera_text = Str()

    #: The Camera column's tooltip: the camera's id, or why it has none.
    camera_tooltip = Str()

    #: When it was saved, in local time.
    saved_at_text = Str()

    #: Whether it is the default of its scope's slot, kept one-hot per slot
    #: by the store.
    is_default = Bool()

    #: Whether it was saved for the loaded device.
    is_current_device = Bool()

    #: Whether its scope covers the selected camera on the loaded device,
    #: so Apply can put it on the live alignment.
    applicable = Bool()

    #: Whether it carries camera-side corners (not endpoint-only).
    has_camera_quad = Bool()

    #: False for a camera's any-device preset that cannot be carried to the
    #: loaded device: its own device's scene rect or this one's is unknown.
    carriable = Bool(True)

    #: The camera frame size it was saved at as [w, h]; None if unknown.
    frame_size = Union(None, List(Float))

    #: Paints the row in the active highlight: an applicable row while
    #: rows that do not apply are listed too.
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

    #: The selected camera; an empty identity with none.
    current_camera = Instance(CameraIdentity, ())

    #: Whether the live alignment may change now — False while a protocol
    #: runs. Gates Apply.
    editable = Bool(True)

    #: List only the presets of the loaded device and the selected camera's
    #: any-device presets.
    this_device_only = Bool(True)

    #: The camera's live frame size as [w, h]; None without a picture.
    #: A preset saved at another picture shape applies its endpoint only.
    live_frame_size = Union(None, List(Float))

    #: The loaded device's scene rect as [x, y, w, h]; None when unknown.
    #: A camera's any-device preset reaches another device only through
    #: both devices' rects.
    current_device_scene_rect = Union(None, List(Float))

    #: Whether the store accepts changes.
    writable = Property(Bool, observe="store.read_only")

    #: Why the store does not, shown above the table; "" while it does.
    notice = Property(Str, observe="store.read_only_reason")

    #: The selected camera and the default preset for it on the loaded
    #: device.
    setup_text = Property(
        Str,
        observe="current_camera, current_device_key, store.presets, store.defaults",
    )

    #: Set by the owner when the live alignment was not made with the
    #: selected camera; "" otherwise.
    setup_notice = Str()

    #: Whether Save as can run: the store writable and no protocol running.
    can_save = Property(Bool, observe="editable, writable")

    #: One row per listed preset: the loaded device's first, then by device
    #: and name.
    rows = List(Instance(AlignmentPresetRow))

    #: The row the table has selected.
    selected = Instance(AlignmentPresetRow)

    #: The selected row's scope label, as the Scope picker edits it.
    selected_scope = Str()

    #: The labels the Scope picker offers for the selected row.
    selected_scope_choices = List(Str)

    #: Why the last scope change was refused, shown in the strip; "" once a
    #: change succeeds.
    scope_notice = Str()

    #: Whether Apply can run on the selected row.
    can_apply = Property(Bool, observe="selected.applicable, editable")

    #: Whether the selected row is its slot's default — a top-level mirror,
    #: since enabled_when misses nested changes.
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

    def _get_setup_text(self):
        camera = self.current_camera
        default = (
            self.store.resolve_default(self.current_device_key, camera)
            if self.store is not None
            else None
        )

        return ALIGNMENT_SETUP_TEMPLATE.format(
            camera=camera.display_text if camera.is_known else NO_CAMERA_TEXT,
            default=f"'{default.name}'"
            if default is not None
            else NO_DEFAULT_PRESET_TEXT,
        )

    # ------------------------------------------------------------------ #
    @observe(
        "store.presets, store.defaults, current_device_key, current_camera, "
        "this_device_only, live_frame_size, current_device_scene_rect"
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
                and (not self.this_device_only or self._listed_here(preset))
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
                    scope=preset.scope,
                    scope_text=ALIGNMENT_PRESET_SCOPE_LABELS.get(
                        preset.scope, preset.scope
                    ),
                    scope_choices=scope_labels_for(
                        preset.camera_label,
                        preset.camera_id,
                        not preset.is_endpoint_only,
                    ),
                    camera=preset.camera,
                    camera_text=self._camera_text(preset),
                    camera_tooltip=self._camera_tooltip(preset),
                    saved_at_text=local_saved_at_text(preset.saved_at),
                    is_default=self.store.is_default(preset.id),
                    applicable=preset.applies_to(self.current_camera, current)
                    and self._carriable_here(preset),
                    carriable=self._carriable_here(preset),
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
        self._show_selected_scope()

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
    def _write_default_through(self, event):
        """Write a default toggled in the table; the store keeps one default
        per slot, and its change rebuilds every row's glyph."""

        if self._syncing or self.store is None:
            return

        row = event.object

        try:
            if row.is_default:
                self.store.set_default(row.preset_id)
            else:
                self.store.clear_default(row.preset_id)
        except (OSError, ValueError) as exc:
            logger.error(f"Could not change the default alignment preset: {exc}")

            # The rebuild puts every row back on the store's defaults.
            self._rebuild_rows()

    @observe("selected")
    def _show_selected_scope(self, event=None):
        """Point the Scope picker at the selected row's scope."""
        row = self.selected

        self._syncing = True

        try:
            if row is None:
                self.selected_scope_choices = list(
                    ALIGNMENT_PRESET_SCOPE_LABELS.values()
                )
                self.selected_scope = ""
            else:
                self.selected_scope_choices = row.scope_choices
                self.selected_scope = row.scope_text
        finally:
            self._syncing = False

    @observe("selected_scope")
    def _write_scope_through(self, event):
        row = self.selected

        if self._syncing or row is None or self.store is None:
            return

        if not event.new or event.new == row.scope_text:
            return

        try:
            scope = scope_code(event.new)
            self.store.set_scope(row.preset_id, scope, self._move_here_for(row, scope))
        except (OSError, ValueError, StopIteration) as exc:
            logger.error(f"Could not change the scope of preset '{row.name}': {exc}")

            self.scope_notice = SCOPE_CHANGE_FAILED_TEMPLATE.format(
                name=row.name, reason=exc
            )
            self._show_selected_scope()

            return

        self.scope_notice = ""

    def _move_here_for(self, row, scope):
        """What binds ``row``'s preset to the loaded device when ``scope``
        ties it to a device and it was saved on another one (a camera's
        any-device preset listed here): its device, scene rect, and scene
        quad and endpoint moved by the two devices' scene rects. None when
        it stays where it is.

        Raises ``ValueError`` when either device's scene rect is unknown.
        """

        if scope == ALIGNMENT_PRESET_SCOPE_CAMERA:
            return None

        if row.device_key == self.current_device_key:
            return None

        preset = self.store.get(row.preset_id)
        here = self.current_device_scene_rect
        scene_quad = quad_between_scene_rects(
            preset.scene_quad, preset.device_scene_rect, here
        )

        if scene_quad is None:
            raise ValueError(PRESET_DEVICE_SIZE_UNKNOWN_NOTE)

        return {
            "device_key": self.current_device_key,
            "device_scene_rect": list(here),
            "scene_quad": scene_quad,
            "endpoint_quad": quad_between_scene_rects(
                preset.endpoint_quad, preset.device_scene_rect, here
            ),
        }

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
    def _listed_here(self, preset):
        """Whether the filtered table lists ``preset``: it was saved for the
        loaded device, or it is the selected camera's any-device preset."""

        if preset.device_key == self.current_device_key:
            return True

        return preset.scope == ALIGNMENT_PRESET_SCOPE_CAMERA and preset.camera.matches(
            self.current_camera
        )

    def _carriable_here(self, preset):
        """Whether ``preset``'s scene quad can be placed on the loaded
        device: its own device, or both devices' scene rects known. Only a
        camera's any-device preset is ever carried to another device."""

        if preset.scope != ALIGNMENT_PRESET_SCOPE_CAMERA:
            return True

        if preset.device_key == self.current_device_key:
            return True

        return (
            preset.device_scene_rect is not None
            and self.current_device_scene_rect is not None
        )

    def _camera_text(self, preset):

        if preset.scope == ALIGNMENT_PRESET_SCOPE_DEVICE:
            return ANY_CAMERA_TEXT

        return preset.camera.display_text

    def _camera_tooltip(self, preset):
        camera = preset.camera

        if preset.scope == ALIGNMENT_PRESET_SCOPE_DEVICE:
            return ANY_CAMERA_TOOLTIP_TEMPLATE.format(
                camera=_quoted(camera) if camera.is_known else NO_CAMERA_TEXT
            )

        if camera.has_stable_id:
            return CAMERA_ID_TOOLTIP_TEMPLATE.format(camera_id=camera.camera_id)

        return CAMERA_WITHOUT_ID_TOOLTIP

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
        some_rows_do_not_apply = any(not row.applicable for row in self.rows)

        for row in self.rows:
            row.is_current_device = row.device_key == self.current_device_key
            row.highlighted = row.applicable and some_rows_do_not_apply
            row.name_error = self._name_error_for(row)
            row.warning = row.name_error or self._applicability_warning_for(row)

    def _name_error_for(self, row):
        if self.store is None:
            return alignment_preset_name_error(row.name)

        return self.store.name_error(row.name, row.device_key, row.preset_id)

    def _applicability_warning_for(self, row):
        """Why Apply cannot put ``row`` (fully) on the live alignment, or ""."""

        if not row.carriable:
            return _sentence(PRESET_DEVICE_SIZE_UNKNOWN_NOTE)

        if not row.applicable:
            if row.scope != ALIGNMENT_PRESET_SCOPE_CAMERA and not row.is_current_device:
                return PRESET_OTHER_DEVICE_WARNING_TEMPLATE.format(
                    device_key=row.device_key
                )

            return PRESET_OTHER_CAMERA_WARNING_TEMPLATE.format(
                camera=_quoted(row.camera)
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

    #: The camera the alignment was made with (shown, not edited).
    camera_text = Str()

    #: Which setups the preset applies to, as a scope label.
    scope_label = Str()

    #: The scope labels this alignment can be saved with.
    scope_choices = List(Str)

    #: What the preset will hold, e.g. that it is endpoint-only.
    note = Str()

    #: Make the saved preset the default of its scope's slot.
    make_default = Bool(False)

    def _get_name_error(self):
        return alignment_preset_name_error(self.name)

    def _get_is_name_valid(self):
        return not self.name_error

    @property
    def scope(self):
        """The chosen scope as an ALIGNMENT_PRESET_SCOPE_* value."""
        return scope_code(self.scope_label)
