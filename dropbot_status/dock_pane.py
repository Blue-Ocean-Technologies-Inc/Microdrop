# enthought imports
from pyface.tasks.dock_pane import DockPane

from .consts import PKG, PKG_name


class DropbotStatusDockPane(DockPane):
    """
    A dock pane to view the status of the dropbot.
    """
    #### 'ITaskPane' interface ################################################

    id = PKG + ".pane"
    name = f"{PKG_name} Dock Pane"

    def create_contents(self, parent):
        # Import all the components from your module
        from .displayed_UI import (
            DropbotStatusViewModelSignals,
            DropBotStatusViewModel,
            DropBotStatusView
        )
        from .model import DropBotStatusModel
        from .dramatiq_UI import DramatiqDropBotStatusViewModel, DramatiqDropBotStatusView, DramatiqDropBotStatusViewModelSignals
        from .dramatiq_dropbot_status_controller import DramatiqDropbotStatusController

        model = DropBotStatusModel()

        # initialize dramatiq controllable dropbot status UI
        dramatiq_view_signals = DramatiqDropBotStatusViewModelSignals()
        dramatiq_view_model = DramatiqDropBotStatusViewModel(
            model=model,
            view_signals=dramatiq_view_signals
        )

        # store controller and view in dock pane
        self.dramatiq_controller = DramatiqDropbotStatusController(ui=dramatiq_view_model,
                                                                   listener_name=dramatiq_view_model.__class__.__module__.split(".")[0] + "_listener")
        self.dramatiq_status_view = DramatiqDropBotStatusView(view_model=dramatiq_view_model)

        # initialize displayed UI
        view_signals = DropbotStatusViewModelSignals()
        view_model = DropBotStatusViewModel(
            model=model,
            view_signals=view_signals
        )

        status_view = DropBotStatusView(view_model=view_model)

        return status_view
