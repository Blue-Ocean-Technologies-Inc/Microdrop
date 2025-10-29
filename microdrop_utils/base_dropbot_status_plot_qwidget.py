import json
import time
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtCore import QTimer, Qt
from microdrop_utils._logger import get_logger
from microdrop_utils.base_dropbot_qwidget import (
    BaseDramatiqControllableDropBotQWidget)

logger = get_logger(__name__)


class BaseDropBotStatusPlotWidget(BaseDramatiqControllableDropBotQWidget):
    """Widget for displaying real-time voltage data with optional twin axis."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.value_tracked_name = kwargs.get('value_tracked_name')
        self.value_tracked_unit = kwargs.get('value_tracked_unit')
        self.second_value_tracked_name = kwargs.get('second_value_tracked_name')
        self.second_value_tracked_unit = kwargs.get('second_value_tracked_unit')

        if self.value_tracked_name is None or self.value_tracked_unit is None:
            raise ValueError(
                "'value_tracked_name' and 'value_tracked_unit' must be set")

        self.init_ui(*args, **kwargs)

    def init_ui(self, *args, **kwargs):
        """Initialize the UI components."""
        # Create main layout
        self.layout = QVBoxLayout()

        # Create plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#2b2b2b')
        if self.second_value_tracked_name:
            self.plot_widget.setTitle(
                f"Real-time {self.value_tracked_name.capitalize()} and {self.second_value_tracked_name.capitalize()} Monitoring", color='w')
        else:
            self.plot_widget.setTitle(
                f"Real-time {self.value_tracked_name.capitalize()} Monitoring", color='w')
        self.plot_widget.setLabel('left', 
                                  f"{self.value_tracked_name.capitalize()}",
                                  units=f"{self.value_tracked_unit}", 
                                  color='w')
        self.plot_widget.showAxis('right')
        self.plot_widget.setLabel('bottom', 'Time (s)', color='w')

        # Enable mouse interaction for zooming and panning
        self.plot_widget.setMouseEnabled(x=True, y=True)

        # Configure Y-axis with major ticks every 50V
        y_axis = self.plot_widget.getAxis('left')
        y_axis.setTickSpacing(major=50, minor=10)
        y_axis.setStyle(tickTextOffset=5)

        # Add grid lines
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.getAxis('left').setTextPen('w')
        self.plot_widget.getAxis('bottom').setTextPen('w')

        # Create first value curve with thicker line
        self.tracked_value_curve = self.plot_widget.plot(
            pen=pg.mkPen(color='y', width=2))

        # Initialize second axis and curve if second value is provided
        if self.second_value_tracked_name and self.second_value_tracked_unit:
            # Create second y-axis
            self.second_axis = pg.ViewBox()
            self.plot_widget.scene().addItem(self.second_axis)
            self.plot_widget.getAxis('right').linkToView(self.second_axis)
            self.second_axis.setXLink(self.plot_widget)
            self.plot_widget.getViewBox().sigResized.connect(self.update_second_axis)
            
            # Create second value curve
            self.second_tracked_value_curve = pg.PlotCurveItem(pen=pg.mkPen(color='c', width=2))
            self.second_axis.addItem(self.second_tracked_value_curve)
            
            # Set up the second axis label
            self.plot_widget.setLabel('right',
                                      f"{self.second_value_tracked_name.capitalize()}",
                                      units=f"{self.second_value_tracked_unit}", 
                                      color='w')
            self.plot_widget.getAxis('right').setTextPen('w')

        # Add horizontal reference lines at key voltage levels
        self.plot_widget.addLine(y=0, pen=pg.mkPen(color='r', style=Qt.DashLine))
        self.plot_widget.addLine(y=50, pen=pg.mkPen(color='r', style=Qt.DashLine))
        self.plot_widget.addLine(y=100, pen=pg.mkPen(color='r', style=Qt.DashLine))
        self.plot_widget.addLine(y=150, pen=pg.mkPen(color='r', style=Qt.DashLine))

        # Add legend
        self.plot_widget.addLegend()

        self.layout.addWidget(self.plot_widget)

        # Data storage
        self.tracked_values = []
        self.second_tracked_values = []
        self.start_time = time.time()
        self.times = []

        # Update timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(100)  # Update every 100ms

        self.setLayout(self.layout)

    def update_second_axis(self):
        self.second_axis.setGeometry(self.plot_widget.getViewBox().sceneBoundingRect())
        self.second_axis.linkedViewChanged(self.plot_widget.getViewBox(), self.second_axis.XAxis)
    
    def update_tracked_value(self, tracked_value_str, is_second_value=False):
        """Update the tracked_value reading."""
        try:
            # Extract numeric value from tracked_value string
            tracked_value = float(tracked_value_str.split()[0])
            
            if is_second_value:
                self.second_tracked_values.append(tracked_value)
            else:
                self.tracked_values.append(tracked_value)

                # update the time of data acquisition
                current_time = time.time() - self.start_time
                if not is_second_value:  # Only append time once
                    self.times.append(current_time)

            # Keep only last 100 seconds of data
            if len(self.tracked_values) > 1000:  # 100 seconds at 10Hz
                self.tracked_values.pop(0)
                self.times.pop(0)
            if len(self.second_tracked_values) > 1000:
                self.second_tracked_values.pop(0)

        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing value: {e}")

    def update_plot(self):
        """Update the plot with current data."""
        if not self.tracked_values:
            return

        self.tracked_value_curve.setData(self.times, self.tracked_values)
        
        if self.second_tracked_values:
            self.second_tracked_value_curve.setData(
                self.times, self.second_tracked_values)

    def _on_capacitance_updated_triggered(self, body):
        data = json.loads(body)
        
        # Update first value
        tracked_value = data.get(self.value_tracked_name, 
                                f'0 {self.value_tracked_unit}')
        self.update_tracked_value(tracked_value)
        
        # Update second value if configured
        if self.second_value_tracked_name:
            second_value = data.get(self.second_value_tracked_name, 
                                    f'0 {self.second_value_tracked_unit}')
            self.update_tracked_value(second_value, is_second_value=True)