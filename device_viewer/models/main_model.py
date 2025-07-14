from traits.api import Property, Str, Enum, observe, Instance, Bool
from .route import RouteLayerManager
from .electrodes import Electrodes

class MainModel(RouteLayerManager, Electrodes):

    # TODO: Move all RouteLayerManager and Electrodes related properties and methods to this class for better comprehension

    # ---------------- Model Traits -----------------------

    # Draw: User can draw a single segment. Switches to draw-edit for extending the segment immediately
    # Edit: User can only extend selected segment
    # Edit-Draw: Same as edit except we switch to draw on mouserelease
    # Auto: Autorouting. User can only autoroute. Switches to edit once path has been created
    # Merge: User can only merge paths. They cannot edit.
    # Channel-Edit: User can edit the channel of an electrode.
    # Display: User can only view the device. No editing allowed.
    # To change the mode, set the mode property and clean up any references/inconsistencies
    mode = Enum("draw", "edit", "edit-draw", "auto", "merge", "channel-edit", "display")

    mode_name = Property(Str, observe="mode")
    editable = Property(Bool, observe="mode")

    message = Str("") # Message to display in the table view

    step_id = Instance(str, allow_none=True) # The step_id of the current step, if any. If None, we are in free mode.
    step_label = Instance(str, allow_none=True) # The label of the current step, if any.

    # ------------------------- Properties ------------------------

    def _get_mode_name(self):
        return {
            "draw": "Draw",
            "edit-draw": "Draw",
            "edit": "Edit",
            "auto": "Autoroute",
            "merge": "Merge",
            "channel-edit": "Channel Edit",
            "display": "Display"
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
    
    # ------------------ Observers ------------------------------------

    @observe('mode')
    def mode_change(self, event):
        if event.old == 'merge' and event.new != 'merge': # We left merge mode
            self.message = ""
            self.layer_to_merge = None
        if event.old == "channel-edit" and event.new != "channel-edit": # We left channel-edit mode
            self.electrode_editing = None