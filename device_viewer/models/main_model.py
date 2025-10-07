from traits.api import Property, Str, Enum, observe, Instance, Bool, List, Float
from pyface.undo.api import UndoManager
import uuid

from traits.has_traits import HasTraits

from device_viewer.models.alpha import AlphaValue
from device_viewer.models.perspective import PerspectiveModel
from microdrop_application.consts import APP_GLOBALS_REDIS_HASH
from .route import RouteLayerManager
from .electrodes import Electrodes
from device_viewer.default_settings import default_alphas

from dramatiq import get_broker
from microdrop_utils.redis_manager import get_redis_hash_proxy
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

class DeviceViewMainModel(HasTraits):

    # Compose device view model using components
    routes = Instance(RouteLayerManager)
    electrodes = Instance(Electrodes)

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
    # To change the mode, set the mode property and clean up any references/inconsistencies
    mode = Enum("draw", "edit", "edit-draw", "auto", "merge", "channel-edit", "display", "camera-place", "camera-edit")


    # Editor related properties
    mode_name = Property(Str, observe="mode")
    editable = Property(Bool, observe="mode")
    message = Str("") # Message to display in the table view

    # calibration related properties
    liquid_capacitance_over_area = Instance(float, allow_none=True)  # The capacitance of the liquid in pF/mm^2
    filler_capacitance_over_area = Instance(float, allow_none=True)  # The capacitance of the filler in pF/mm^2
    electrode_scale = Property(Float, observe='electrodes.svg_model.area_scale')

    # message model properties
    step_id = Instance(str, allow_none=True) # The step_id of the current step, if any. If None, we are in free mode.
    step_label = Instance(str, allow_none=True) # The label of the current step, if any.
    free_mode = Bool(True)  # Whether we are in free mode (no step_id)

    uuid = str(uuid.uuid4())  # The uuid of the model. Used to figure out if a state message is from this model or not.

    # ------------------ Alpha Color Model --------------------
    alpha_map = List() # We store the dict as a list since TraitsUI doesnt support dicts

    # ------------------ Camera Model --------------------
    camera_perspective = Instance(PerspectiveModel, PerspectiveModel())

    # ------------------ Initialization --------------------

    def traits_init(self):
        """Initialize the model with default traits."""

        self.electrodes = Electrodes()
        self.routes = RouteLayerManager(message=self.message, mode=self.mode)
        # Initialize the alpha map with default values
        self.alpha_map = [AlphaValue(key=key, alpha=default_alphas[key]) for key in default_alphas.keys()]

    # ------------------------- Properties ------------------------

    def _get_electrode_scale(self):
        return self.electrodes.svg_model.area_scale

    def _set_electrode_scale(self, value):
        self.electrodes.svg_model.area_scale = value

    def _get_mode_name(self):
        return {
            "draw": "Draw",
            "edit-draw": "Draw",
            "edit": "Edit",
            "auto": "Autoroute",
            "merge": "Merge",
            "channel-edit": "Channel Edit",
            "display": "Display",
            "camera-edit": "Camera Edit",
            "camera-place": "Camera Place"
        }.get(self.mode, "Error")

    def _get_editable(self):
        return self.mode != "display"

    def _set_editable(self, value: bool):
        if not value:
            self.mode = "display"
        elif self.mode == "display":
            self.mode = "edit"  # Default to edit mode if editable is set to True

    # ------------------------ Methods ---------------------------------

    def reset(self):
        self.electrodes.reset_electrode_states()
        self.routes.reset_route_manager()

    def get_alpha(self, key: str) -> float:
        """Get the alpha value for a given key."""
        for alpha_value in self.alpha_map:
            if alpha_value.key == key:
                return alpha_value.alpha if alpha_value.visible else 0.0
        return 1.0 # Default alpha if not found

    def set_alpha(self, key: str, alpha: float):
        """Set the alpha value for a given key."""
        for alpha_value in self.alpha_map:
            if alpha_value.key == key:
                alpha_value.alpha = alpha
                return
        # If not found, add a new alpha value
        self.alpha_map.append(AlphaValue(key=key, alpha=alpha))

    def set_visible(self, key: str, visible: bool):
        """Set the visibility of a given alpha value."""
        for alpha_value in self.alpha_map:
            if alpha_value.key == key:
                alpha_value.visible = visible
                return

    # ------------------ Observers ------------------------------------

    @observe('mode')
    def mode_change(self, event):
        if event.old == 'merge' and event.new != 'merge': # We left merge mode
            self.message = ""
            self.routes.layer_to_merge = None
        if event.old == "channel-edit" and event.new != "channel-edit": # We left channel-edit mode
            self.electrodes.electrode_editing = None
        if event.old != "camera-place" and event.new == "camera-place":
            self.camera_perspective.reset_rects() # Reset the rectangles when entering camera-place mode
            self.set_visible("electrode_fill", False)  # Set the fill alpha low for visibility
            self.set_visible("electrode_text", False)  # Set the text alpha low for visibility
            self.set_visible("electrode_outline", True)  # Keep the outline visible for editing
        if (event.old == "camera-edit" or event.old == "camera-place") and event.new != "camera-edit" and event.new != "camera-place": # We left camera-edit mode
            self.set_visible("electrode_fill", True)  # Restore fill visibility
            self.set_visible("electrode_text", True)  # Restore text

    @observe("routes.layers.items.route.route.items")
    @observe("electrodes.channels_electrode_ids_map.items")
    def update_route_label(self, event):
        """
        Update label for electrodes path based on channel for electrodes.
        """
        if self.routes is not None:
            for layer in self.routes.layers:
                if layer.route.route:
                    # Update the name of the route layer based on the current channel map
                    layer.name = layer.route.get_name(self.electrodes.channels_electrode_ids_map)
                else:
                    layer.name = "Null route"


    # @observe("electrodes.channel_electrode_areas_scaled_map")
    # def push_globals(self, event):
    #
    #     if event.new != event.old:
    #         logger.info(f"push_globals: {event.name}: {event.new}")
    #         app_globals = get_redis_hash_proxy(redis_client=get_broker().client, hash_name=APP_GLOBALS_REDIS_HASH)
    #         if event.name == "channel_electrode_areas_scaled_map":
    #             app_globals["channel_electrode_areas"] = event.new

    @observe('electrode_scale')
    def update_stored_capacitances_on_area_scale_change(self, event):
        # new_area = old_area * new_scale ==> cap/new_area = cap/(old_area * new_scale) = old_cap_over_area / new_scale
        if event.new:
            self.liquid_capacitance_over_area /= event.new
            self.filler_capacitance_over_area /= event.new