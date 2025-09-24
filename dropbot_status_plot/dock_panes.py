# enthought imports
from pyface.tasks.dock_pane import DockPane

from dropbot_status.dramatiq_dropbot_status_controller import DramatiqDropbotStatusController

from microdrop_utils.base_dropbot_status_plot_qwidget import BaseDropBotStatusPlotWidget

from .consts import PKG, PKG_name, CAPACITANCE_LISTENER, VOLTAGE_LISTENER, VOLTAGE_CAPACITANCE_LISTENER


class DropbotStatusCapacitancePlotDockPane(DockPane):
    """
    A dock pane to view the status of the dropbot.
    """
    #### 'ITaskPane' interface ################################################

    id = PKG + "_capacitance.pane"
    name = PKG_name + " Capacitance Dock Pane"

    def create_contents(self, parent):
        view = BaseDropBotStatusPlotWidget(value_tracked_name="capacitance",
                                           value_tracked_unit="pF",
                                           controller_dramatiq_listener_name=CAPACITANCE_LISTENER)

        # we can use the same controller as the basic dramatiq dropbot status plugin
        view.controller = DramatiqDropbotStatusController

        return view


class DropbotStatusVoltagePlotDockPane(DockPane):
    """
    A dock pane to view the status of the dropbot.
    """
    #### 'ITaskPane' interface ################################################

    id = PKG + "_voltage.pane"
    name = PKG_name + " Voltage Dock Pane"

    def create_contents(self, parent):
        view = BaseDropBotStatusPlotWidget(value_tracked_name="voltage",
                                           value_tracked_unit="V",
                                           controller_dramatiq_listener_name=VOLTAGE_LISTENER)

        # we can use the same controller as the basic dramatiq dropbot status plugin
        view.controller = DramatiqDropbotStatusController

        return view


class DropbotStatusVoltageCapacitancePlotDockPane(DockPane):
    """
    A dock pane to view the status of the dropbot.
    """
    #### 'ITaskPane' interface ################################################

    id = PKG + "_voltage_capacitance.pane"
    name = PKG_name + " Voltage Capacitance Dock Pane"

    def create_contents(self, parent):
        view = BaseDropBotStatusPlotWidget(value_tracked_name="voltage",
                                           value_tracked_unit="V",
                                           second_value_tracked_name="capacitance",
                                           second_value_tracked_unit="pF",
                                           controller_dramatiq_listener_name=VOLTAGE_CAPACITANCE_LISTENER)

        # we can use the same controller as the basic dramatiq dropbot status plugin
        view.controller = DramatiqDropbotStatusController

        return view