import os
import sys

from device_viewer.models.electrodes import Electrodes
from examples.qt_device_viewer.device_viewer_widget import DeviceViewerWidget
from examples.tests.common import TEST_PATH

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from functools import partial
from PySide6.QtWidgets import QApplication
import sys

from microdrop_utils._logger import get_logger
logger = get_logger(__name__)

if not QApplication.instance():
    app = QApplication(sys.argv)
else:
    app = QApplication.instance()

device_viewer_widget = DeviceViewerWidget()

# from the file dialog button
default_paths = [
    f"{TEST_PATH}{os.sep}device_svg_files{os.sep}2x3device.svg",
    f"{TEST_PATH}{os.sep}device_svg_files{os.sep}device_drc.svg"
]

selected_svg_path = default_paths[0]

electrodes_model = Electrodes()
electrodes_model.set_electrodes_from_svg_file(selected_svg_path)

device_viewer_widget.change_active_layer(electrodes_model)


# Connect the electrode layer events

def __on_electrode_clicked(_electrode_view):
    """Handle the event when an electrode is clicked."""
    logger.debug(f"Electrode {_electrode_view.electrode} clicked")

    # update the model
    _electrode_view.electrode.state = not _electrode_view.electrode.state

    # update the view
    _electrode_view.update_color(_electrode_view.electrode.state)

    # Do some other notification or updates or action here...


################### Handler Method Connections ####################################

for electrode_view in device_viewer_widget.current_electrode_layer.electrode_views.values():
    electrode_view.on_electrode_left_clicked = partial(__on_electrode_clicked, electrode_view)


device_viewer_widget.show()
sys.exit(app.exec())
