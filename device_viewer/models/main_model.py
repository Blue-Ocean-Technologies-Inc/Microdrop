from traits.api import Property, Str, Enum, observe, Instance
from .route import RouteLayerManager
from .electrodes import Electrodes

class MainModel(RouteLayerManager, Electrodes):

    # ---------------- Model Traits -----------------------

    # Draw: User can draw a single segment. Switches to draw-edit for extending the segment immediately
    # Edit: User can only extend selected segment
    # Edit-Draw: Same as edit except we switch to draw on mouserelease
    # Auto: Autorouting. User can only autoroute. Switches to edit once path has been created
    # Merge: User can only merge paths. They cannot edit.
    mode = Enum("draw", "edit", "edit-draw", "auto", "merge", "channel-edit")

    mode_name = Property(Str, observe="mode")

    message = Str("")

    step_id = Instance(str, allow_none=True)

    # ------------------------- Properties ------------------------

    def _get_mode_name(self):
        return {
            "draw": "Draw",
            "edit-draw": "Draw",
            "edit": "Edit",
            "auto": "Autoroute",
            "merge": "Merge",
            "channel-edit": "Channel Edit"
        }.get(self.mode, "Error")
    
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