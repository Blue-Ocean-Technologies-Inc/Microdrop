# enthought imports
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QHBoxLayout
from pyface.tasks.dock_pane import DockPane

from .consts import PKG, PKG_name,DEVICE_NAME


class PeripheralStatusDockPane(DockPane):
    """
    A dock pane to view the status of the dropbot.
    """
    #### 'ITaskPane' interface ################################################

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    def create_contents(self, parent):
        # Import all the components from your module
        from .z_stage.view_model import ZStageViewModel, ZStageViewModelSignals
        from .z_stage.view import ZStageView
        from .model import PeripheralModel
        from .dramatiq_view_model import DramatiqStatusViewModel
        from .dramatiq_status_controller import DramatiqStatusController

        model = PeripheralModel(device_name=DEVICE_NAME)

        # initialize dramatiq controller for the UI
        dramatiq_view_model = DramatiqStatusViewModel(model=model)
        # store controller and view in dock pane
        self.dramatiq_controller = DramatiqStatusController(ui=dramatiq_view_model,
                                                                   listener_name=dramatiq_view_model.__class__.__module__.split(".")[0] + "_listener")

        # initialize displayed UI
        view_signals = ZStageViewModelSignals()
        view_model = ZStageViewModel(
            model=model,
            view_signals=view_signals
        )

        _view = ZStageView(view_model=view_model)

        view_model.force_initial_update()

        ### Make pane scrollable:

        # The scroll area needs an intermediate QWidget to hold the layout
        # This is what allows you to use 'addStretch'
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)  # Pass content widget to layout constructor
        layout.addWidget(_view)
        layout.addStretch()

        # Create the scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(scroll_content)

        # Return the scroll area directly
        return scroll_area