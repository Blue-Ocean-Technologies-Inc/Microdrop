from traits.api import Property, Str, Enum, observe, Instance, Bool, List, Float, HasTraits, Event, UUID
from pyface.undo.api import UndoManager

from device_viewer.models.alpha import AlphaValue
from device_viewer.models.perspective import PerspectiveModel
from .calibration import CalibrationModel
from .route import RouteLayerManager
from .electrodes import Electrodes
from ..default_settings import electrode_fill_key, electrode_text_key, electrode_outline_key

from ..preferences import DeviceViewerPreferences

from logger.logger_service import get_logger
from ..utils.camera import qpointf_list_serialize, qpointf_list_deserialize

logger = get_logger(__name__)


class DeviceViewMainModel(HasTraits):

    # Compose device view model using components
    routes = Instance(RouteLayerManager)
    electrodes = Instance(Electrodes)
    preferences = Instance(DeviceViewerPreferences)
    calibration = Instance(CalibrationModel)
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
    mode = Enum("draw", "edit", "edit-draw", "auto", "merge", "channel-edit", "display", "camera-place", "camera-edit", "pan")
    last_mode = Enum("draw", "edit", "edit-draw", "auto", "merge", "channel-edit", "display", "camera-place", "camera-edit", "pan")

    # Editor related properties
    mode_name = Property(Str, observe="mode")
    editable = Property(Bool, observe="mode")
    message = Str("") # Message to display in the table view

    last_capacitance = Property(Float, depends_on="calibration.last_capacitance")
    liquid_capacitance_over_area = Property(Float, depends_on="calibration.liquid_capacitance_over_area")
    filler_capacitance_over_area = Property(Float, depends_on="calibration.filler_capacitance_over_area")

    electrode_scale = Property(Float, observe='electrodes.svg_model.area_scale')

    # message model properties
    step_id = Instance(str, allow_none=True) # The step_id of the current step, if any. If None, we are in free mode.
    step_label = Instance(str, allow_none=True) # The label of the current step, if any.
    free_mode = Bool(True)  # Whether we are in free mode (no step_id)

    uuid = UUID(desc="The uuid of the model. Used to figure out if a state message is from this model or not.")

    # -------------------------------------- events ----------------------------------
    zoom_in_event = Event(desc="Increase device view scale -- zoom into device view")
    zoom_out_event = Event(desc="Decrease device view scale -- zoom out of device view")
    reset_view_event = Event(desc="Reset device view scaling -- reset zoom")

    # --------------------------------- Alpha Color Model --------------------------------
    alpha_map = List() # We store the dict as a list since TraitsUI doesnt support dicts

    # ------------------ Camera Model --------------------
    camera_perspective = Instance(PerspectiveModel, PerspectiveModel())

    def load_camera_perspective_from_preferences(self):
        _reference_rect = qpointf_list_deserialize(self.preferences.preferences.get("camera.reference_rect", "[]"))
        _transformed_reference_rect = qpointf_list_deserialize(self.preferences.preferences.get("camera.transformed_reference_rect", "[]"))

        if _reference_rect:
            self.camera_perspective.reference_rect = _reference_rect

        if _transformed_reference_rect:
            self.camera_perspective.transformed_reference_rect = _transformed_reference_rect

    # ------------------ Initialization --------------------
    def traits_init(self):
        """Initialize the model with default traits."""

        self.electrodes = Electrodes()
        self.routes = RouteLayerManager(message=self.message, mode=self.mode)
        self.calibration = CalibrationModel(electrodes=self.electrodes)
        # Initialize the alpha map with default values

        if self.preferences:
            self.alpha_map = [AlphaValue(key=key, alpha=self.preferences.default_alphas[key],
                                         visible=self.preferences.default_visibility[key])
                              for key in self.preferences.default_alphas.keys()]

    # ------------------------- Properties ------------------------

    def _get_electrode_scale(self):
        if self.electrodes.svg_model is not None:
            return self.electrodes.svg_model.area_scale
        return None

    def _set_electrode_scale(self, value):
        if self.electrodes.svg_model is not None:
            self.electrodes.svg_model.area_scale = value

    def _get_mode_name(self):
        return self.mode.title().replace('-', ' ')

    def _get_editable(self):
        return self.mode != "display"

    def _set_editable(self, value: bool):
        if not value:
            self.mode = "display"
        elif self.mode == "display":
            self.mode = "edit"  # Default to edit mode if editable is set to True

    def _get_last_capacitance(self):
        return self.calibration.last_capacitance

    def _get_liquid_capacitance_over_area(self):
        return self.calibration.liquid_capacitance_over_area

    def _get_filler_capacitance_over_area(self):
        return self.calibration.filler_capacitance_over_area

    def _set_last_capacitance(self, value):
        self.calibration.last_capacitance = value

    def _set_liquid_capacitance_over_area(self, value):
        self.calibration.liquid_capacitance_over_area = value

    def _set_filler_capacitance_over_area(self, value):
        self.calibration.filler_capacitance_over_area = value

    # ------------------------ Methods ---------------------------------

    def reset(self):
        self.electrodes.clear_electrode_states()
        self.routes.clear_routes()

    def get_alpha(self, key: str) -> float:
        """Get the alpha value for a given key."""
        for alpha_value in self.alpha_map:
            if alpha_value.key == key:
                return alpha_value.alpha / 100 if alpha_value.visible else 0.0
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

    def goto_last_mode(self):
        logger.debug(f"Going to last mode: {self.last_mode}")
        self.mode = self.last_mode

    def flip_mode_activation(self, mode):
        """
        Method to enter mode if it is different from the current mode.
        Exits mode to last mode if mode is current mode.
        """
        if self.mode == mode:
            logger.debug(f"Current mode is given mode ({mode}), reverting to last mode ({self.last_mode}).")
            self.goto_last_mode()
        else:
            logger.debug(f"Current mode ({self.mode}) is not given mode ({mode}), setting given mode")
            self.mode = mode

    def measure_filler_capacitance(self):
        """measuring filler capacitance."""
        self.calibration.measure_filler_capacitance()

    def measure_liquid_capacitance(self):
        """P measuring liquid capacitance."""
        self.calibration.measure_liquid_capacitance()

    # ------------------ Observers ------------------------------------

    @observe('mode')
    def mode_change(self, event):
        logger.debug(f"Mode change. New mode is: {event.new}")
        # Do not store last mode when moving between the two camera alignment modes.
        # They are one "super" mode.
        if not (event.old == 'camera-edit' and event.new == 'camera-place') and not (event.new == 'camera-edit' and event.old == 'camera-place'):
            logger.debug(f"Setting last mode to {event.old}")
            self.last_mode = event.old # for use in goto_last_mode method

        if event.old == 'merge' and event.new != 'merge': # We left merge mode
            self.message = ""
            self.routes.layer_to_merge = None
        if event.old == "channel-edit" and event.new != "channel-edit": # We left channel-edit mode
            self.electrodes.electrode_editing = None
        if event.old != "camera-place" and event.new == "camera-place":
            self.camera_perspective.reset_rects() # Reset the rectangles when entering camera-place mode
            self.set_visible(electrode_fill_key, False)  # Set the fill alpha low for visibility
            self.set_visible(electrode_text_key, False)  # Set the text alpha low for visibility
            self.set_visible(electrode_outline_key, True)  # Keep the outline visible for editing
        # if (event.old == "camera-edit" or event.old == "camera-place") and event.new != "camera-edit" and event.new != "camera-place": # We left camera-edit mode
        #     self.set_visible(electrode_fill_key, True)  # Restore fill visibility
        #     self.set_visible(electrode_text_key, True)  # Restore text

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
            if self.liquid_capacitance_over_area:
                self.liquid_capacitance_over_area /= event.new

            if self.filler_capacitance_over_area:
                self.filler_capacitance_over_area /= event.new

    ### update default alpha values with current values for persistence
    @observe("alpha_map.items.[alpha, visible]")
    def _alpha_values_changed(self, event):
        change_type = event.name

        if change_type == "alpha":
            self.preferences.default_alphas[event.object.key] = event.new

        elif change_type == "visible":
            self.preferences.default_visibility[event.object.key] = event.new

    @observe("camera_perspective:transformation")
    def _camera_perspective_changed(self, event=None):
        self.preferences.preferences.set("camera.reference_rect", qpointf_list_serialize(self.camera_perspective.reference_rect))
        self.preferences.preferences.set("camera.transformed_reference_rect", qpointf_list_serialize(self.camera_perspective.transformed_reference_rect))