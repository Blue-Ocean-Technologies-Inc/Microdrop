# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Camera Alignment window's Presets strip and the Save Alignment
Preset naming dialog.

The strip names the selected camera and its default here (and warns when
the shown alignment was not made with it) above the table of saved
presets — the name editable in place, the scope and camera of each, the
default toggled by clicking its glyph, any problem shown beside it — and
the action buttons, with a Scope picker for the selected preset. The
naming dialog keeps OK disabled while the name breaks the naming rule; a
name the device already uses asks to replace the preset or rename the
new one."""

# Enthought library imports.
from traitsui.api import (
    Action,
    EnumEditor,
    Group,
    HGroup,
    Item,
    Label,
    TableEditor,
    UItem,
    VGroup,
    View,
    spring,
)

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import NO, YES, confirm

# Microdrop style imports.
from microdrop_style.colors import WARNING_COLOR

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    ActiveRowCheckboxColumn,
    ActiveRowObjectColumn,
    HtmlLabelEditor,
)

# Local imports.
from ...consts import ALIGNMENT_PRESETS_TITLE, SAVE_ALIGNMENT_PRESET_DIALOG_TITLE

#: The strip's title, bold like the panes' headers.
PRESETS_TITLE_STYLE_SHEET = "QLabel { font-weight: bold; }"

#: Why the presets cannot be changed, in the warning colour.
NOTICE_TEMPLATE = (
    f'<span style="color: {WARNING_COLOR}; font-weight: bold;">{{}}</span>'
)


class CameraColumn(ActiveRowObjectColumn):
    """The Camera column: each row's tooltip names its camera's id, or
    says it has none."""

    def get_tooltip(self, object):
        return object.camera_tooltip


alignment_presets_table_editor = TableEditor(
    columns=[
        ActiveRowObjectColumn(
            name="name",
            label="Name",
            active_trait="highlighted",
            width=0.2,
            tooltip="Double-click to rename the preset",
        ),
        ActiveRowObjectColumn(
            name="scope_text",
            label="Applies to",
            active_trait="highlighted",
            editable=False,
            width=0.14,
            tooltip="Which setups the preset applies to; change it with the "
            "Scope picker above",
        ),
        CameraColumn(
            name="camera_text",
            label="Camera",
            active_trait="highlighted",
            editable=False,
            width=0.14,
        ),
        ActiveRowObjectColumn(
            name="device_key",
            label="Device",
            active_trait="highlighted",
            editable=False,
            width=0.12,
        ),
        ActiveRowObjectColumn(
            name="saved_at_text",
            label="Saved",
            active_trait="highlighted",
            editable=False,
            width=0.12,
        ),
        ActiveRowCheckboxColumn(
            name="is_default",
            label="Default",
            active_trait="highlighted",
            horizontal_alignment="center",
            width=0.06,
            tooltip="Click to make this preset the default of its scope (its "
            "camera on its device, its device, or its camera); click again "
            "to clear it",
        ),
        ActiveRowObjectColumn(
            name="warning",
            label="Warning",
            active_trait="highlighted",
            editable=False,
            width=0.22,
        ),
    ],
    selected="selected",
    dclick="double_clicked",
    sortable=False,
    deletable=False,
    edit_on_first_click=False,
    show_toolbar=False,
)

alignment_presets_view = View(
    VGroup(
        HGroup(
            Group(
                Label(ALIGNMENT_PRESETS_TITLE), style_sheet=PRESETS_TITLE_STYLE_SHEET
            ),
            Item(
                "this_device_only",
                label="This device only",
                tooltip="List only the loaded device's presets (and the "
                "selected camera's any-device presets)",
            ),
            spring,
            Item(
                "selected_scope",
                label="Scope",
                editor=EnumEditor(name="selected_scope_choices"),
                enabled_when="writable and selected is not None",
                tooltip="Which setups the selected preset applies to",
            ),
            UItem(
                "save_as_button",
                enabled_when="can_save",
                tooltip="Save the confirmed alignment as a named preset",
            ),
            UItem(
                "apply_button",
                enabled_when="can_apply",
                tooltip="Put the selected preset on the live alignment "
                "(also double-click its row)",
            ),
            UItem(
                "set_default_button",
                enabled_when="writable and selected is not None "
                "and not selected_is_default",
                tooltip="Make the selected preset the default of its scope",
            ),
            UItem(
                "clear_default_button",
                enabled_when="writable and selected_is_default",
                tooltip="Leave the selected preset's scope without a default",
            ),
            UItem(
                "delete_button",
                enabled_when="writable and selected is not None",
                tooltip="Delete the selected preset",
            ),
        ),
        UItem("setup_text", style="readonly"),
        UItem(
            "setup_notice",
            editor=HtmlLabelEditor(template=NOTICE_TEMPLATE),
            visible_when="setup_notice",
        ),
        UItem(
            "notice",
            editor=HtmlLabelEditor(template=NOTICE_TEMPLATE),
            visible_when="notice",
        ),
        UItem("rows", editor=alignment_presets_table_editor),
    ),
    resizable=True,
)

alignment_preset_name_view = View(
    VGroup(
        Item("name", label="Preset name"),
        Item("name_error", style="readonly", show_label=False),
        Item("device_key", style="readonly", label="Device"),
        Item("camera_text", style="readonly", label="Camera"),
        Item(
            "scope_label",
            label="Applies to",
            editor=EnumEditor(name="scope_choices"),
            tooltip="This camera on this device, this device through any "
            "camera, or this camera on any device",
        ),
        Item("note", style="readonly", show_label=False, visible_when="note"),
        Item("make_default", label="Make it the default for these setups"),
    ),
    title=SAVE_ALIGNMENT_PRESET_DIALOG_TITLE,
    buttons=[Action(name="OK", enabled_when="is_name_valid"), "Cancel"],
    kind="livemodal",
    resizable=True,
    width=380,
)


def ask_alignment_preset_name(model, find_existing, parent=None):
    """Show the naming dialog for ``model`` until the user picks a name.

    ``find_existing(name)`` returns the device's preset already called
    ``name``, or None. Return True to replace that preset, False when the
    name is free, or None when the user cancels.
    """
    while True:
        ui = model.edit_traits(view=alignment_preset_name_view, parent=parent)

        if not ui.result:
            return None

        existing = find_existing(model.name)

        if existing is None:
            return False

        answer = confirm(
            parent,
            f"{model.device_key} already has a preset named '{existing.name}'. "
            f"Replace it with the current alignment?",
            title=SAVE_ALIGNMENT_PRESET_DIALOG_TITLE,
            yes_label="Replace",
            no_label="Rename",
        )

        # "Rename" reopens the naming dialog; closing the prompt cancels.
        if answer == YES:
            return True

        if answer != NO:
            return None


if __name__ == "__main__":
    # Standalone prototyping: both views against their models over a
    # throwaway store. Save as... opens the naming dialog.
    import tempfile
    from pathlib import Path

    from traits.api import HasTraits, Instance, observe

    from device_viewer.models.alignment_preset import AlignmentPreset
    from device_viewer.models.alignment_preset_store import AlignmentPresetStore
    from device_viewer.models.alignment_preset_table import (
        AlignmentPresetName,
        AlignmentPresetTable,
        scope_labels_for,
    )
    from device_viewer.models.camera_identity import CameraIdentity
    from device_viewer.utils.camera_endpoints import CameraEndpointStore

    QUAD = [[0.0, 0.0], [100.0, 0.0], [100.0, 80.0], [0.0, 80.0]]
    CAMERA = CameraIdentity(camera_id="usb#demo", label="Demo Camera")

    def demo_snapshot(device_key, scope="device", camera=CAMERA):
        return AlignmentPreset(
            device_key=device_key,
            scope=scope,
            camera_id=camera.camera_id,
            camera_label=camera.label,
            frame_size=[640.0, 480.0],
            camera_quad=QUAD,
            scene_quad=QUAD,
            endpoint_quad=QUAD,
        )

    class PresetsDemo(HasTraits):
        """Stands in for the workflow controller behind the strip."""

        table = Instance(AlignmentPresetTable)

        @observe("table:save_as_button")
        def _save_as(self, event):
            store, device_key = self.table.store, self.table.current_device_key
            choices = scope_labels_for(CAMERA.label, CAMERA.camera_id, True)
            naming = AlignmentPresetName(
                name=store.next_default_name(device_key),
                device_key=device_key,
                camera_text=CAMERA.display_text,
                scope_label=choices[0],
                scope_choices=choices,
            )
            replace = ask_alignment_preset_name(
                naming, lambda name: store.find_named(device_key, name)
            )

            if replace is not None:
                store.save_named(
                    naming.name,
                    demo_snapshot(device_key, naming.scope),
                    replace=replace,
                )

        @observe("table:apply_requested")
        def _apply(self, event):
            print(f"apply {event.new.name}")

    with tempfile.TemporaryDirectory() as directory:
        store = AlignmentPresetStore(
            path=Path(directory) / "alignment_presets.json",
            endpoint_store=CameraEndpointStore(path=Path(directory) / "e.json"),
        )
        store.refresh()

        twin = CameraIdentity(camera_id="usb#twin", label="Demo Camera")

        for device_key, name, scope, camera in [
            ("demo-device", "bench", "camera_device", CAMERA),
            ("demo-device", "twin camera", "camera_device", twin),
            ("demo-device", "after cleaning", "device", CAMERA),
            ("other-device", "mount", "camera", CAMERA),
            ("other-device", "bench", "device", CAMERA),
        ]:
            store.save_named(name, demo_snapshot(device_key, scope, camera))

        demo = PresetsDemo(
            table=AlignmentPresetTable(
                store=store, current_device_key="demo-device", current_camera=CAMERA
            )
        )
        demo.table.configure_traits(view=alignment_presets_view)
