from PySide6.QtWidgets import QApplication
from traitsui.api import View, Item, TableEditor, UIInfo, UItem, HGroup, VGroup, Label, RangeEditor
from traitsui.key_bindings import KeyBindings, KeyBinding

from device_viewer.views.route_selection_view.menu import RouteLayerMenu
from device_viewer.models.route import RouteLayer

from microdrop_utils.traitsui_qt_helpers import ColorColumn, VisibleColumn, ObjectColumn, CustomCheckboxColumn, \
    SafeCancelTableHandler, DoubleSpinBoxEditor, make_table_row_header_resizable

from logger.logger_service import get_logger

logger = get_logger(__name__)

class RouteLayerTableHandler(SafeCancelTableHandler):
    # For these handlers, info is as usual, and rows is a list of rows that the action is acting on
    # In the case of the right click menu, always a list of size 1 with the affected row

    def init(self, info: UIInfo):
        """Runs once when the UI is generated."""
        super().init(info)

        # Columns are interactive; extend that to the row-number header too
        make_table_row_header_resizable(info.layers.table_view)

        return True

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

        if hasattr(info.object.routes, "selected_layer"):
            info.object.routes.selected_layer = None

        super().handle_escape(info)


class RunColumn(CustomCheckboxColumn):
    def formatter(self, value):
        return "play_arrow" if value else "play_disabled"


layer_table_editor = TableEditor(
    columns=[
        ObjectColumn(name="name", label="Path", resize_mode="interactive", editable=False),
        VisibleColumn(
            name="visible",
            label="",
            editable=False,
            horizontal_alignment="center",
            resize_mode="interactive",
        ),
        RunColumn(
            name="selected_for_run",
            label="Run",
            editable=False,
            horizontal_alignment="center",
            resize_mode="interactive",
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
UItem('object.routes.duration',
      editor=DoubleSpinBoxEditor(low=0.0, high=10000.0, decimals=1, step=0.1),
      tooltip="Duration of each step in route (seconds)"),
UItem('object.routes.trail_length',
      editor=RangeEditor(low=1, high=10000, mode='spinner'),
      tooltip="Length of each step in route (# electrodes)"),
UItem('object.routes.trail_overlay',
      editor=RangeEditor(low=0, high_name='object.routes.max_trail_overlay', mode='spinner'),
      tooltip="electrodes actuated from one step to overlay onto next step"),
UItem('object.routes.repetitions',
      editor=RangeEditor(low=1, high=10000, mode='spinner'),
      enabled_when="not object.routes_repeats_frozen",
      tooltip="Times to repeat loops execution"),
UItem('object.routes.repeat_duration',
      editor=RangeEditor(low=0, high=10000, mode='spinner'),
      enabled_when="not object.routes_repeats_frozen",
      tooltip="Seconds to repeat path executions. Idle time in end if loop cannot be completed"),
)

protocol_execution_settings_header = (
Label("Duration", tooltip="Duration of each step in route (seconds)"),
Label("Length", tooltip="Length of each step in route (# electrodes)"),
Label("Overlay", tooltip="electrodes actuated from one step to overlay onto next step"),
Label("Reps", tooltip="Times to repeat path executions"),
Label("Rep Duration", tooltip="Seconds to repeat path executions. Idle time in end if loop cannot be completed"),
)

soft_transition_settings = (
UItem('object.routes.soft_start', tooltip="Ramp up overlay at start"),
UItem('object.routes.soft_terminate', tooltip="Ramp down overlay at end"),
UItem('object.routes.linear_repeats', tooltip="Replay linear paths Repetitions times"),
)
soft_transition_settings_header = (
Label("Ramp Up", tooltip="Ramp up overlay at start"),
Label("Ramp Dn", tooltip="Ramp down overlay at end"),
Label("Lin Reps", tooltip="Replay linear paths Repetitions times"),
)


protocol_execution_settings_group = VGroup(
    HGroup(
        VGroup(protocol_execution_settings_header[0], protocol_execution_settings[0]),
        VGroup(protocol_execution_settings_header[1], protocol_execution_settings[1]),
        VGroup(protocol_execution_settings_header[2], protocol_execution_settings[2]),
    ),
    HGroup(
        VGroup(protocol_execution_settings_header[3], protocol_execution_settings[3]),
        VGroup(protocol_execution_settings_header[4], protocol_execution_settings[4]),
    ),
    HGroup(
        VGroup(soft_transition_settings_header[0], soft_transition_settings[0]),
        VGroup(soft_transition_settings_header[1], soft_transition_settings[1]),
        VGroup(soft_transition_settings_header[2], soft_transition_settings[2]),
    ),
    # enabled_when='free_mode',
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
    UItem(
        "object.routes.commit_to_step_btn",
        tooltip="Apply execution params to step",
        enabled_when="object.routes_commit_enabled",
        visible_when=f"not {executing}",
        springy=True,
    ),  # commit to step
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

if __name__ == "__main__":
    # demo view
    import sys

    from traits.api import HasTraits, Bool, DelegatesTo, Instance, Str, observe

    from device_viewer.models.route import Route, RouteLayerManager
    from microdrop_style.helpers import style_app

    class RouteSelectionDemoModel(HasTraits):
        """Stand-in for DeviceViewMainModel exposing only the traits
        RouteLayerView / ExecutionSettingsView bind to."""

        routes = Instance(RouteLayerManager, ())

        # Execution state (normally driven by RouteExecutionService)
        route_execution_service_executing = Bool(False)
        route_execution_service_paused = Bool(False)
        execution_status = Str("")

        protocol_running = Bool(False)

        # Top-level mirrors for enabled_when bindings (nested paths like
        # `object.routes.commit_enabled` don't re-evaluate reliably)
        routes_commit_enabled = DelegatesTo("routes", prefix="commit_enabled")
        routes_repeats_frozen = DelegatesTo("routes", prefix="repeats_frozen")

        @observe("routes.execute_path_requested")
        def _log_execute_path_requested(self, event):
            logger.info(f"Execute path requested for layers: {event.new}")

    demo_model = RouteSelectionDemoModel()

    # A few sample layers: a linear path, a loop, and a short path
    demo_model.routes.add_layer(Route(route=["a", "b", "c"]))
    demo_model.routes.add_layer(Route(route=["d", "e", "f", "d"]))
    demo_model.routes.add_layer(Route(route=["g", "h"]))

    # channel_map: channel id -> list of electrode ids
    demo_channel_map = {channel: [electrode_id] for channel, electrode_id in enumerate("abcdefgh")}
    for demo_layer in demo_model.routes.layers:
        demo_layer.name = demo_layer.route.get_name(demo_channel_map)

    app = QApplication.instance() or QApplication(sys.argv)
    style_app(app)

    # Same pattern as the device viewer dock pane: both views edit one model
    layer_ui = demo_model.edit_traits(view=RouteLayerView)
    execution_settings_ui = demo_model.edit_traits(view=ExecutionSettingsView)

    sys.exit(app.exec())