from traits.api import Float, Property, Instance
from traits.trait_types import self
from traitsui.api import View, Item, HGroup, VGroup, Label, Action, Controller
from device_viewer.services.electrode_interaction_service import ElectrodeInteractionControllerService

SetScaleButton = Action(name="Set Scale", action="set_electrode_area_scale")

scale_edit_view = View(
        HGroup(
            # --- Left Side: Electrode Info (Read-only) ---
            VGroup(
                Label("Electrode Information"),
                Item('id', style='readonly', label="ID"),
                Item('channel', style='readonly', label="Channel"),
                Item('area_scaled', style='readonly', label="Current Area (mm²)", format_str="%.4f"),
                show_border=True,
            ),
            # --- Right Side: Scaling Controls ---
            VGroup(
                Label("Scale Calculation"),
                Item('controller.real_electrode_area', label="Measured Area (mm²)"),
                Item('controller.scaling_factor', style='readonly', label="Scaling Factor", format_str="%.4f"),
                show_border=True,
            )
        ),
        title="Electrode Area Scaler",
        buttons=[SetScaleButton, 'Cancel'],
        resizable=True
    )


class ScaleEditViewController(Controller):
    # --- User input ---
    real_electrode_area = Float(1.0)  # User sets this value
    electrode_interaction_service = Instance(ElectrodeInteractionControllerService)

    # --- Calculated Property ---
    scaling_factor = Property(Float, observe=['real_electrode_area', 'model.area_scaled'])

    def _get_scaling_factor(self):
        """Calculates the scaling factor to be displayed."""
        if self.model.area_scaled > 0:
            return self.real_electrode_area / self.model.area_scaled
        return 0.0

    # --- TraitsUI View Definition ---
    view = scale_edit_view

    def set_electrode_area_scale(self, info):
        self.electrode_interaction_service.model.electrode_scale = self.scaling_factor
        info.ui.dispose()