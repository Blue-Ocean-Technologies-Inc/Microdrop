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
        from .widget import (
            DropBotStatusModel,
            DropbotStatusViewModelSignals,
            DropBotStatusViewModel,
            DropBotStatusView
        )

        # --- Instantiate the MVVM components ---
        model = DropBotStatusModel()
        view_signals = DropbotStatusViewModelSignals()

        view_model = DropBotStatusViewModel(
            model=model,
            view_signals=view_signals
        )

        # The View is the UI component we are testing
        status_view = DropBotStatusView(view_signals=view_signals)

        return status_view
