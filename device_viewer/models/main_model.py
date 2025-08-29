from traits.api import Property, Str, Enum, observe, Instance, Bool, List, Float
from pyface.undo.api import UndoManager
import uuid

from device_viewer.models.alpha import AlphaValue
from device_viewer.models.perspective import PerspectiveModel
from .route import RouteLayerManager
from .electrodes import Electrodes
from device_viewer.default_settings import default_alphas

class MainModel(RouteLayerManager, Electrodes):

    # TODO: Move all RouteLayerManager and Electrodes related properties and methods to this class for better comprehension

    # ---------------- Model Traits -----------------------

    undo_manager = Instance(UndoManager)  # Undo manager for the model

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
    electrode_scale = Float(1.0)  # The scale of the electrode area in pixels to mm

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

    def traits_init(self, **traits):
        """Initialize the model with default traits."""
        super().traits_init(**traits)

        # Initialize the alpha map with default values
        self.alpha_map = [AlphaValue(key, default_alphas[key]) for key in default_alphas.keys()]

    # ------------------------- Properties ------------------------

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
        self.reset_electrode_states()
        self.reset_route_manager()

    def get_alpha(self, key: str) -> float:
        """Get the alpha value for a given key."""
        for alpha_value in self.alpha_map:
            if alpha_value.value == key:
                return alpha_value.alpha if alpha_value.visible else 0.0
        return 1.0 # Default alpha if not found
    
    def set_alpha(self, key: str, alpha: float):
        """Set the alpha value for a given key."""
        for alpha_value in self.alpha_map:
            if alpha_value.value == key:
                alpha_value.alpha = alpha
                return
        # If not found, add a new alpha value
        self.alpha_map.append(AlphaValue(value=key, alpha=alpha))

    def set_visible(self, key: str, visible: bool):
        """Set the visibility of a given alpha value."""
        for alpha_value in self.alpha_map:
            if alpha_value.value == key:
                alpha_value.visible = visible
                return
    
    # ------------------ Observers ------------------------------------

    @observe('mode')
    def mode_change(self, event):
        if event.old == 'merge' and event.new != 'merge': # We left merge mode
            self.message = ""
            self.layer_to_merge = None
        if event.old == "channel-edit" and event.new != "channel-edit": # We left channel-edit mode
            self.electrode_editing = None
        if event.old != "camera-place" and event.new == "camera-place":
            self.camera_perspective.reset_rects() # Reset the rectangles when entering camera-place mode
            self.set_visible("electrode_fill", False)  # Set the fill alpha low for visibility
            self.set_visible("electrode_text", False)  # Set the text alpha low for visibility
            self.set_visible("electrode_outline", True)  # Keep the outline visible for editing
        if (event.old == "camera-edit" or event.old == "camera-place") and event.new != "camera-edit" and event.new != "camera-place": # We left camera-edit mode
            self.set_visible("electrode_fill", True)  # Restore fill visibility
            self.set_visible("electrode_text", True)  # Restore text visibility