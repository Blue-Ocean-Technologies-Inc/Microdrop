from traits.api import Interface, Instance, Enum, Property, Str, Bool, Float, Event, List, UUID
from pyface.undo.undo_manager import UndoManager

from .i_route_execution_service import IRouteExecutionService
from ..preferences import DeviceViewerPreferences
from ..models.calibration import CalibrationModel
from ..models.perspective import PerspectiveModel
from ..models.electrodes import Electrodes
from ..models.route import RouteLayerManager


class IDeviceViewMainModel(Interface):

    # Compose device view model using components
    routes = Instance(RouteLayerManager)
    electrodes = Instance(Electrodes)
    preferences = Instance(DeviceViewerPreferences)
    calibration = Instance(CalibrationModel)

    # add services
    route_execution_service = Instance(IRouteExecutionService)
    # route Execution state
    route_execution_service_executing = Bool(False)
    route_execution_service_paused = Bool(False)

    # route Execution status display
    execution_status = Str("")

    # ---------------- Device View Traits -----------------------

    undo_manager = Instance(UndoManager)  # Undo manager

    # Draw: User can draw a single segment. Switches to draw-edit for extending the segment immediately
    # Edit: User can only extend selected segment
    # Edit-Draw: Same as edit except we switch to draw on mouserelease
    # Auto: Autorouting. User can only autoroute. Switches to edit once path has been created
    # Merge: User can only merge paths. They cannot edit.
    # Channel-Edit: User can edit the channel of an electrode.
    # Display: User can only view the device. No editing allowed.
    # Camera-Edit: User can edit the perspecive correction of the camera feed
    # Pan: User can pan svg device (useful when zoomed in)
    # To change the mode, set the mode property and clean up any references/inconsistencies
    mode = Enum(
        "draw",
        "edit",
        "edit-draw",
        "auto",
        "merge",
        "channel-edit",
        "display",
        "camera-place",
        "camera-edit",
        "pan",
    )
    last_mode = Enum(
        "draw",
        "edit",
        "edit-draw",
        "auto",
        "merge",
        "channel-edit",
        "display",
        "camera-place",
        "camera-edit",
        "pan",
    )

    # Editor related properties
    mode_name = Property(Str, observe="mode")
    editable = Property(Bool, observe="mode")
    message = Str("")  # Message to display in the table view

    last_capacitance = Property(Float, depends_on="calibration.last_capacitance")
    liquid_capacitance_over_area = Property(
        Float, depends_on="calibration.liquid_capacitance_over_area"
    )
    filler_capacitance_over_area = Property(
        Float, depends_on="calibration.filler_capacitance_over_area"
    )

    electrode_scale = Property(Float, observe="electrodes.svg_model.area_scale")

    # mode properties
    step_id = Instance(
        str, allow_none=True
    )  # The step_id of the current step, if any. If None, we are in free mode.
    step_label = Instance(
        str, allow_none=True
    )  # The label of the current step, if any.
    free_mode = Bool(True)  # Whether we are in free mode (no step_id)
    protocol_running = Bool(False)  # is protocol running
    realtime_mode = Bool(False)
    connected = Bool(False)  # is dropbot connected

    uuid = UUID(
        desc="The uuid of the model. Used to figure out if a state message is from this model or not."
    )

    # -------------------------------------- events ----------------------------------
    zoom_in_event = Event(
        desc="Increase device view scale -- zoom into device view"
    )
    zoom_out_event = Event(
        desc="Decrease device view scale -- zoom out of device view"
    )
    reset_view_event = Event(desc="Reset device view scaling -- reset zoom")

    # --------------------------------- Alpha Color Model --------------------------------
    alpha_map = (
        List()
    )  # We store the dict as a list since TraitsUI doesnt support dicts

    # ------------------ Camera Model --------------------
    camera_perspective = Instance(PerspectiveModel)