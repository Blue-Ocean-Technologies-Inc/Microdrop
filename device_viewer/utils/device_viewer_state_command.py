from traits.api import Instance, Str
from pyface.undo.abstract_command import AbstractCommand

from .message_utils import gui_models_to_message_model

class DeviceViewerStateCommand(AbstractCommand):

    name = Str("Restore State")

    def do(self):
        self._state = gui_models_to_message_model(self.data.electrodes_model, self.data.route_layer_manager)
        print(f"Stored state: {self._state}")

    def undo(self):
        self.data.apply_message_model(self._state)
