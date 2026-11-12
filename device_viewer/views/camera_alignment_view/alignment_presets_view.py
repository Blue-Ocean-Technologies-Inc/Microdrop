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

The strip is the table of saved presets — the name editable in place, the
default toggled by clicking its glyph, any problem shown beside it — over
the action buttons. The naming dialog keeps OK disabled while the name
breaks the naming rule; a name the device already uses asks to replace
the preset or rename the new one."""

# Enthought library imports.
from traitsui.api import (
    Action,
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

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    ActiveRowCheckboxColumn,
    ActiveRowObjectColumn,
)

# Local imports.
from ...consts import ALIGNMENT_PRESETS_TITLE, SAVE_ALIGNMENT_PRESET_DIALOG_TITLE

#: The strip's title, bold like the panes' headers.
PRESETS_TITLE_STYLE_SHEET = "QLabel { font-weight: bold; }"

alignment_presets_table_editor = TableEditor(
    columns=[
        ActiveRowObjectColumn(
            name="name",
            label="Name",
            active_trait="highlighted",
            width=0.28,
            tooltip="Double-click to rename the preset",
        ),
        ActiveRowObjectColumn(
            name="device_key",
            label="Device",
            active_trait="highlighted",
            editable=False,
            width=0.2,
        ),
        ActiveRowObjectColumn(
            name="saved_at_text",
            label="Saved",
            active_trait="highlighted",
            editable=False,
            width=0.16,
        ),
        ActiveRowCheckboxColumn(
            name="is_default",
            label="Default",
            active_trait="highlighted",
            horizontal_alignment="center",
            width=0.08,
            tooltip="Click to make this preset its device's default; "
            "click again to clear it",
        ),
        ActiveRowObjectColumn(
            name="warning",
            label="Warning",
            active_trait="highlighted",
            editable=False,
            width=0.28,
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
                tooltip="List only the loaded device's presets",
            ),
            spring,
            UItem(
                "save_as_button",
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
                enabled_when="selected is not None and not selected_is_default",
                tooltip="Make the selected preset its device's default",
            ),
            UItem(
                "clear_default_button",
                enabled_when="selected_is_default",
                tooltip="Leave the selected preset's device without a default",
            ),
            UItem(
                "delete_button",
                enabled_when="selected is not None",
                tooltip="Delete the selected preset",
            ),
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
        Item("note", style="readonly", show_label=False, visible_when="note"),
        Item("make_default", label="Make it this device's default"),
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
    )
    from device_viewer.utils.camera_endpoints import CameraEndpointStore

    QUAD = [[0.0, 0.0], [100.0, 0.0], [100.0, 80.0], [0.0, 80.0]]

    def demo_snapshot(device_key):
        return AlignmentPreset(
            device_key=device_key, scene_quad=QUAD, endpoint_quad=QUAD
        )

    class PresetsDemo(HasTraits):
        """Stands in for the workflow controller behind the strip."""

        table = Instance(AlignmentPresetTable)

        @observe("table:save_as_button")
        def _save_as(self, event):
            store, device_key = self.table.store, self.table.current_device_key
            naming = AlignmentPresetName(
                name=store.next_default_name(device_key), device_key=device_key
            )
            replace = ask_alignment_preset_name(
                naming, lambda name: store.find_named(device_key, name)
            )

            if replace is not None:
                store.save_named(
                    naming.name, demo_snapshot(device_key), replace=replace
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

        for device_key, name in [
            ("demo-device", "bench"),
            ("demo-device", "after cleaning"),
            ("other-device", "bench"),
        ]:
            store.save_named(name, demo_snapshot(device_key))

        demo = PresetsDemo(
            table=AlignmentPresetTable(store=store, current_device_key="demo-device")
        )
        demo.table.configure_traits(view=alignment_presets_view)
