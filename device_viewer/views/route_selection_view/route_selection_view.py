from traitsui.api import View, Item, TableEditor, UIInfo, UItem, HGroup, VGroup, Label
from traitsui.key_bindings import KeyBindings, KeyBinding

from device_viewer.views.route_selection_view.menu import RouteLayerMenu
from device_viewer.models.route import RouteLayer

from microdrop_utils.pyface_helpers import SafeCancelTableHandler
from microdrop_utils.traitsui_qt_helpers import ColorColumn, VisibleColumn, ObjectColumn, CustomCheckboxColumn

from logger.logger_service import get_logger
logger = get_logger(__name__)

class RouteLayerTableHandler(SafeCancelTableHandler):
    # For these handlers, info is as usual, and rows is a list of rows that the action is acting on
    # In the case of the right click menu, always a list of size 1 with the affected row

    def execute_path(self, info: UIInfo, rows: list[RouteLayer]):
        """Request execution of the selected path via the RouteLayerManager event."""
        info.object.routes.execute_path_requested = [rows[0]]

    def invert_layer(self, info: UIInfo, rows: list[RouteLayer]):
        rows[0].route.invert()

    def delete_layer(self, info, rows):
        info.object.routes.delete_layer(rows[0])

    def start_merge_layer(self, info, rows):
        info.object.routes.layer_to_merge = rows[0]
        info.object.routes.mode = "merge"

    def merge_layer(self, info, rows):
        if info.object.routes.layer_to_merge == None: # Sanity check
            self.cancel_merge_route(info, rows)
            return

        info.object.routes.merge_layer(rows[0])

    def cancel_merge_layer(self, info, rows):
        info.object.routes.mode = "edit"

    ##### ---------------- Key Handlers ------------ #####
    def handle_delete_key(self, info: UIInfo, *args, **kwargs):
        """Called when the user presses the Delete key."""
        # The TableEditor automatically keeps info.object.selected_layer updated
        selected = getattr(info.object.routes, "selected_layer", None)

        if selected:
            logger.info(f"Deleting selected layer: {selected}")
            # Route it through your existing deletion logic on the model
            info.object.routes.delete_layer(selected)

    def handle_escape(self, info: UIInfo):
        """Swallows the Escape key press so the table doesn't hide."""

        if hasattr(info.object, "selected_layer"):
            info.object.routes.selected_layer = None

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
        CustomCheckboxColumn(
            name="selected_for_run",
            label="Run",
            editable=False,
            horizontal_alignment="center",
            width=16,
        ),
    ],
    menu=RouteLayerMenu,
    show_lines=False,
    selected="object.routes.selected_layer",
    sortable=False,
    reorderable=True,
    show_column_labels=True,
    show_row_labels=True,
)

# Width for the whole table needs to be set in the widget itself (in the pane's create_contents)

protocol_execution_settings = (
UItem('object.routes.duration', tooltip="Duration of each step in route (seconds)"),
UItem('object.routes.trail_length', tooltip="Length of each step in route (# electrodes)"),
UItem('object.routes.trail_overlay', tooltip="electrodes actuated from one step to overlay onto next step"),
UItem('object.routes.repetitions', tooltip="Times to repeat path executions"),
)
protocol_execution_settings_header = (
Label("Duration", tooltip="Duration of each step in route (seconds)"),
Label("Length", tooltip="Length of each step in route (# electrodes)"),
Label("Overlay", tooltip="electrodes actuated from one step to overlay onto next step"),
Label("Reps", tooltip="Times to repeat path executions"),
)

soft_transition_settings = (
UItem('object.routes.soft_start', tooltip="Ramp up overlay at start"),
UItem('object.routes.soft_terminate', tooltip="Ramp down overlay at end"),
)
soft_transition_settings_header = (
Label("Ramp Up", tooltip="Ramp up overlay at start"),
Label("Ramp Dn", tooltip="Ramp down overlay at end"),
)


protocol_execution_settings_group = VGroup(
    HGroup(
        VGroup(protocol_execution_settings_header[0], protocol_execution_settings[0]),
        VGroup(protocol_execution_settings_header[1], protocol_execution_settings[1]),
        VGroup(protocol_execution_settings_header[2], protocol_execution_settings[2]),
        VGroup(protocol_execution_settings_header[3], protocol_execution_settings[3]),
    ),
    HGroup(
        VGroup(soft_transition_settings_header[0], soft_transition_settings[0]),
        VGroup(soft_transition_settings_header[1], soft_transition_settings[1]),
    ),
    enabled_when='free_mode',
)

ExecutionSettingsView = View(
    protocol_execution_settings_group,
    resizable=True,
)

# --- Execution control button groups (mutually exclusive via visible_when) ---
# pause / executing trait names from main model
paused = "object.route_execution_service_paused"
executing = "object.route_execution_service_executing"

run_controls = HGroup(
    UItem(
        "object.routes.run_routes",
        tooltip="Run selected routes",
        visible_when=f"not {executing}",
        springy=True,
    ),  # run
    UItem(
        "object.routes.prev_phase_btn",
        tooltip="Previous phase",
        visible_when=paused,
        springy=True,
    ),  # previous phase
    UItem(
        "object.routes.resume_btn",
        tooltip="Resume execution",
        visible_when=f"{executing} and {paused}",
        springy=True,
    ),  # resume
    UItem(
        "object.routes.pause_btn",
        tooltip="Pause execution",
        visible_when=f"{executing} and not {paused}",
        springy=True,
    ),  # pause
    UItem(
        "object.routes.next_phase_btn",
        tooltip="Next phase",
        visible_when=paused,
        springy=True,
    ),  # next phase
    UItem(
        "object.routes.stop_btn",
        tooltip="Stop execution",
        visible_when=executing,
        springy=True,
    ),  # stop
    enabled_when="not object.protocol_running",
)

execution_status_bar = HGroup(
    Item('execution_status', style='readonly', show_label=False),
    visible_when=executing,
    # style_sheet='* { font-size: 15px; }',
)

RouteLayerView = View(
    VGroup(
        run_controls,
        execution_status_bar,
        Item('object.routes.layers', editor=layer_table_editor, show_label=False),
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
