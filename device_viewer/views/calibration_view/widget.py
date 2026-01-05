
from traits.api import HasTraits, Instance, observe
from win32cryptcon import szOID_OIWSEC_dsaCommSHA

from device_viewer.models.calibration import CalibrationModel

from pyface.qt.QtWidgets import (QWidget, QLabel, QPushButton, QToolButton, QHBoxLayout,
                               QVBoxLayout, QSizePolicy)

from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QApplication

from microdrop_style.button_styles import get_button_style
from microdrop_style.helpers import style_app, get_complete_stylesheet, is_dark_mode

def get_toolbutton_with_text_tooltip(text, tooltip):
    btn = QToolButton()
    btn.setText(text)
    btn.setToolTip(tooltip)
    return btn

def format_value(value):


    if value >= 99.5:
        unit_html = "nF/mm<sup>2</sup>"
        value = value / 1000


    elif value <= 0.01:
        unit_html = "fF/mm<sup>2</sup>"
        value = value * 1000

    else:
        unit_html = "pF/mm<sup>2</sup>"


    value = f"{value:.2g}"

    return f"{value} {unit_html}"

class CalibrationWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.cl_btn = get_toolbutton_with_text_tooltip("humidity_high", "Measure Liquid Capacitance")
        self.cf_btn = get_toolbutton_with_text_tooltip("airwave", "Measure filler Capacitance")
        self.refresh_btn = get_toolbutton_with_text_tooltip("reset_wrench", "Reset Measurements")

        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.cl_btn.setCursor(Qt.PointingHandCursor)
        self.cf_btn.setCursor(Qt.PointingHandCursor)

        self.l_label = QLabel()
        self.f_label = QLabel()

        # 1. Top Row: F-Calibration
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(self.cf_btn)
        row1.addWidget(self.f_label)
        row1.addStretch()  # Pushes the label against the button

        # 2. Bottom Row: L-Calibration
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(self.cl_btn)
        row2.addWidget(self.l_label)
        row2.addStretch()

        # 3. Left Column
        left_col = QVBoxLayout()
        left_col.setSpacing(5)
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.addLayout(row1)
        left_col.addLayout(row2)

        # 4. Main Layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(20)  # This is the FIXED distance to the Refresh button

        # Add the labels/calibration group
        main_layout.addLayout(left_col)

        # Add the refresh button
        main_layout.addWidget(self.refresh_btn)

        # Trailing Stretch
        # This acts as a spring that grows. Since it's at the end,
        # it pushes everything before it to the left.
        main_layout.addStretch(1)

        # Ensure the widget itself doesn't try to fill the whole vertical space
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        # apply initial styling and update whenever app color scheme changes
        self.apply_styling()
        QApplication.styleHints().colorSchemeChanged.connect(self.apply_styling)

    def apply_styling(self):
        toolbtn_style = get_button_style(theme="dark" if is_dark_mode() else "light", button_type="tool")
        for btns in [self.cl_btn, self.cf_btn]:
            btns.setStyleSheet(toolbtn_style)

        self.refresh_btn.setStyleSheet(
            toolbtn_style.replace("font-size: 18px; width: 18px; height: 24px;", "font-size: 36px; width: 36px;")
        )

    def display_values(self, liquid_val, filler_val):

        c_l = '<b>C<sub>l</sub></b>'
        c_f = '<b>C<sub>f</sub></b>'
        liquid_text = f"{c_l}: {format_value(liquid_val)}" if liquid_val is not None else f"{c_l}: -"
        filler_text = f"{c_f}: {format_value(filler_val)}" if filler_val is not None else f"{c_f}: -"

        self.l_label.setText(liquid_text)
        self.f_label.setText(filler_text)


class CalibrationController(HasTraits):

    model = Instance(CalibrationModel)
    view = Instance(CalibrationWidget)

    def traits_init(self):
        # --- UI -> Model Signals ---

        # 1. Refresh / Reset Button (Right side)
        self.view.refresh_btn.clicked.connect(self.model.reset)

        # 2. Filler Button (Top Left - Wave Icon)
        # Connects the click to a specific handler for measuring 'filler'
        self.view.cf_btn.clicked.connect(self.model.measure_filler_capacitance)

        # 3. Liquid Button (Bottom Left - Droplet Icon)
        # Connects the click to a specific handler for measuring 'liquid'
        self.view.cl_btn.clicked.connect(self.model.measure_liquid_capacitance)

        self.refresh_ui()

    @observe("model:[liquid_capacitance_over_area, filler_capacitance_over_area]")
    def refresh_ui(self, event=None):
        self.view.display_values(self.model.liquid_capacitance_over_area, self.model.filler_capacitance_over_area)


if __name__ == "__main__":
    import sys

    from pathlib import Path
    from examples.tests.common import TEST_PATH

    from device_viewer.models.electrodes import Electrodes


    # test formatter:

    def run_format_test():
        test_values = [
            24534,
            4234.56342,
            125.16854,
            99.55634,
            99.5,
            99.42456,
            98.64685,
            12.1564,
            1.234567,
            0.12345,
            0.08798789,
            0.005678,
            0.0001234,
            0.00500,
            0.0052120
        ]

        print(f"{'ORIGINAL':<15}           | {'FORMATTED':<15}")
        print("-" * 45)

        for value in test_values:
            orig_str = str(value)
            formatted_str = format_value(value)
            # :<15 forces a width of 15 characters, left-aligned
            print(f"{orig_str:<15} pF / mm^2 | {formatted_str:<15}")

    run_format_test()

    # test app:
    app = QApplication.instance() or QApplication(sys.argv)
    style_app(app)

    # Setup
    electrodes = Electrodes()
    new_filename = Path(TEST_PATH) / "test_svg_model_save_init_scale.svg"
    electrodes.set_electrodes_from_svg_file(new_filename)

    model = CalibrationModel(electrodes=electrodes)

    view = CalibrationWidget()
    presenter = CalibrationController(model=model, view=view)

    view.setStyleSheet(get_complete_stylesheet("dark" if is_dark_mode() else "light"))
    view.show()
    sys.exit(app.exec_())

