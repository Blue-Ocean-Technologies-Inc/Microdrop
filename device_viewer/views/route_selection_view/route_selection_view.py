from traitsui.api import View, VGroup, Item, TableEditor, UIInfo
from traitsui.key_bindings import KeyBindings, KeyBinding

from device_viewer.views.route_selection_view.menu import RouteLayerMenu
from device_viewer.models.route import RouteLayer

from microdrop_utils.pyface_helpers import SafeCancelTableHandler
from microdrop_utils.traitsui_qt_helpers import ColorColumn, VisibleColumn, ObjectColumn

from logger.logger_service import get_logger
logger = get_logger(__name__)

class RouteLayerTableHandler(SafeCancelTableHandler):
    # For these handlers, info is as usual, and rows is a list of rows that the action is acting on
    # In the case of the right click menu, always a list of size 1 with the affected row

    def invert_layer(self, info: UIInfo, rows: list[RouteLayer]):
        rows[0].route.invert()

    def delete_layer(self, info, rows):
        info.object.delete_layer(rows[0])

    def start_merge_layer(self, info, rows):
        info.object.layer_to_merge = rows[0]
        info.object.mode = "merge"

    def merge_layer(self, info, rows):
        if info.object.layer_to_merge == None: # Sanity check
            self.cancel_merge_route(info, rows)
            return

        info.object.merge_layer(rows[0])

    def cancel_merge_layer(self, info, rows):
        info.object.mode = "edit"

    ##### ---------------- Key Handlers ------------ #####
    def handle_delete_key(self, info: UIInfo, *args, **kwargs):
        """Called when the user presses the Delete key."""
        # The TableEditor automatically keeps info.object.selected_layer updated
        selected = getattr(info.object, "selected_layer", None)

        if selected:
            logger.info(f"Deleting selected layer: {selected}")
            # Route it through your existing deletion logic on the model
            info.object.delete_layer(selected)

    def handle_escape(self, info: UIInfo):
        """Swallows the Escape key press so the table doesn't hide."""

        if hasattr(info.object, "selected_layer"):
            info.object.selected_layer = None

        super().handle_escape(info)


layer_table_editor = TableEditor(
    columns=[
        ObjectColumn(name="name", label="Path", resize_mode="stretch", editable=False),
        VisibleColumn(
            name="visible",
            label="",
            editable=False,
            horizontal_alignment="center",
            width=16,
        ),
        ObjectColumn(
            name="trail_overlay",
            label="Overlay",
            editable=True,
            horizontal_alignment="center",
            width=55,
        ),
        ObjectColumn(
            name="trail_length",
            label="Trail",
            editable=True,
            horizontal_alignment="center",
            width=45,
        ),
        ObjectColumn(
            name="duration",
            label="Duration",
            editable=True,
            horizontal_alignment="center",
            width=60,
        ),
        ObjectColumn(
            name="repetitions",
            label="Repeats",
            editable=True,
            horizontal_alignment="center",
            width=55,
        ),
    ],
    menu=RouteLayerMenu,
    show_lines=False,
    selected="selected_layer",
    sortable=False,
    reorderable=True,
    show_column_labels=True,
    show_row_labels=True,
)

# Width for the whole table needs to be set in the widget itself (in the pane's create_contents)
RouteLayerView = View(
        VGroup(
            Item('message', style='readonly', show_label=False),
            Item('layers', editor=layer_table_editor, show_label=False)
        ),
        resizable=True,
        title="Route Layer Selector",
        handler=RouteLayerTableHandler,
        key_bindings=KeyBindings(
            KeyBinding(
                binding1='Delete',
                method_name='handle_delete_key'
            ),
    )
)
