"""TraitsUI view for the Manage Plugins dialog."""
from traitsui.api import Label, OKCancelButtons, TableEditor, UItem, VGroup, View

from microdrop_utils.traitsui_qt_helpers import CustomCheckboxColumn, ObjectColumn

groups_table = TableEditor(
    columns=[
        CustomCheckboxColumn(name="enabled", label="Enabled", editable=False,
                             horizontal_alignment="center"),
        ObjectColumn(name="label", label="Plugin group", editable=False),
    ],
    editable=True,
    sortable=False,
    auto_size=True,   # size columns to their contents so no cell text is clipped
)

manage_plugins_view = View(
    VGroup(
        Label("Tick a group to load it now; untick to unload. "
              "Choices persist across launches."),
        UItem("rows", editor=groups_table),
    ),
    title="Manage Plugins",
    width=420,
    height=260,
    resizable=True,
    buttons=OKCancelButtons,
    kind="livemodal",
)
