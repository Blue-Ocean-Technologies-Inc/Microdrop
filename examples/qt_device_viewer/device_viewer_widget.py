from PySide6.QtCore import QSize
from PySide6.QtGui import QSurfaceFormat

from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget, QPushButton, QGraphicsScene, QBoxLayout, QLabel, QGroupBox, QGridLayout, \
    QSpinBox, QFileDialog

from device_viewer.models.electrodes import Electrodes
from device_viewer.utils.auto_fit_graphics_view import AutoFitGraphicsView
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from microdrop_utils._logger import get_logger

import os

logger = get_logger(__name__)


class DeviceViewerWidget(QWidget):
    """
    A widget for viewing the device
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        # Create a QGraphicsView and a scene
        self.scene = QGraphicsScene(self)
        self.view = AutoFitGraphicsView(self.scene)
        self.view.setObjectName('device_view')
        self.set_frame_active(False)

        self.gl = QOpenGLWidget()
        self.format = QSurfaceFormat()
        self.format.setSamples(4)
        self.view.setViewport(self.gl)

        self.layout = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.setLayout(self.layout)

        # Device view
        self.layout.addWidget(self.view)

        # Status
        self.status_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)

        # fix the size constraint of height
        self.status_layout.setSizeConstraint(QBoxLayout.SizeConstraint.SetFixedSize)
        self.voltage_label = QLabel('Voltage: 0.0 V')
        self.status_layout.addWidget(self.voltage_label, stretch=0)
        self.layout.addLayout(self.status_layout, stretch=0)

        # Manual Controls
        self.manual_group_box = QGroupBox('Manual Controls')
        self.layout.addWidget(self.manual_group_box)
        self.manual_layout = QGridLayout()
        self.manual_group_box.setLayout(self.manual_layout)

        row = 0

        # Voltage
        self.manual_layout.addWidget(QLabel('Voltage:'), row, 0)
        self.voltage_spinbox = QSpinBox()
        self.voltage_spinbox.setSuffix('V')
        self.voltage_spinbox.setRange(0, 140)
        self.manual_layout.addWidget(self.voltage_spinbox, row, 1)

        # Frequency
        self.manual_layout.addWidget(QLabel('Frequency:'), row := row + 1, 0)
        self.frequency_spinbox = QSpinBox()
        self.frequency_spinbox.setRange(0, 20000)
        self.frequency_spinbox.setStepType(QSpinBox.StepType.AdaptiveDecimalStepType)
        self.frequency_spinbox.setSuffix('Hz')
        self.frequency_spinbox.setValue(10000)
        self.manual_layout.addWidget(self.frequency_spinbox, row, 1)

        self.manual_layout.addWidget(QLabel('Threshold:'), row := row + 1, 0)

        self.current_electrode_layer = None

        # button for selecting svg file
        self.svg_path_button = QPushButton('Select SVG File', self)
        self.svg_path_button.clicked.connect(self.open_file_dialog)
        self.layout.addWidget(self.svg_path_button)

    def open_file_dialog(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(self, "Select SVG File", "", "SVG Files (*.svg);;All Files (*)", options=options)
        if file_name:
            new_electrodes_model = Electrodes()
            new_electrodes_model.set_electrodes_from_svg_file(file_name)
            self.change_active_layer(new_electrodes_model)
            self.svg_path_button.setText(os.path.basename(file_name))

    def collapse_manual_controls(self, checked):
        if checked:
            for i in range(self.manual_layout.count()):
                self.manual_layout.itemAt(i).widget().show()
        else:
            for i in range(self.manual_layout.count()):
                self.manual_layout.itemAt(i).widget().hide()

    def set_voltage(self, voltage: float):
        self.voltage_label.setText(f'Voltage: {voltage:.2f} V')

    def set_frame_active(self, active: bool):
        if active:
            self.set_frame_colour('green')
        else:
            self.set_frame_colour('red')

    def set_frame_colour(self, colour: str):
        self.view.setStyleSheet(f'#device_view {{ border: 5px solid {colour}; }}')

    def change_active_layer(self, electrodes_model: 'Electrodes'):

        # create a new layer
        # obtain proper path using the index for the path in svg combo box that should correspond to the same index
        # in the device svg manager
        new_electrode_layer = ElectrodeLayer("layer1", electrodes_model)

        # remove the current layer
        self.remove_current_layer()

        # add the new electrode layer
        self.add_layer(new_electrode_layer)
        logger.debug(f"Layer {new_electrode_layer.id} added -> {electrodes_model.svg_model.filename}")

        # set the current electrode layer to this new electrode layer
        self.current_electrode_layer = new_electrode_layer

        # bound the new svg
        self.scene.setSceneRect(self.scene.itemsBoundingRect())

        # Trigger an update to redraw and re-initialize the svg widget manually
        # TODO: Find a less hacky way to implement this
        self.resize(QSize(self.width() + 1, self.height() + 1))

    def remove_current_layer(self):
        if len(self.scene.items()) > 1:
            self.scene.removeItem(self.current_electrode_layer)
            logger.debug("Removed current electrode layer")
            self.scene.clear()
            logger.debug("Removed current electrode layer")
            self.current_electrode_layer = None
            self.scene.update()

    def add_layer(self, layer: 'ElectrodeLayer'):
        self.scene.addItem(layer)