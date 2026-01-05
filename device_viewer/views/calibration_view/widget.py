from traits.api import HasTraits, Instance, observe
from pyface.qt.QtWidgets import QWidget, QLabel, QPushButton, QHBoxLayout, QSizePolicy

from device_viewer.models.calibration import CalibrationModel


class CalibrationWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.l_label = QLabel("C_l: -")
        self.f_label = QLabel("C_f: -")
        self.refresh_btn = QPushButton("refresh")

        layout = QHBoxLayout(self)
        layout.addWidget(self.l_label)
        layout.addWidget(self.f_label)
        layout.addWidget(self.refresh_btn)
        layout.addStretch()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def display_values(self, liquid_text, filler_text):
        self.l_label.setText(liquid_text)
        self.f_label.setText(filler_text)


class CalibrationController(HasTraits):

    model = Instance(CalibrationModel)
    view = Instance(CalibrationWidget)

    def traits_init(self):

        # UI -> Model
        self.view.refresh_btn.clicked.connect(self.model.reset)

        # Model -> UI (Traits observation)
        self.model.observe(self.refresh_ui, "liquid_capacitance_over_area")
        self.model.observe(self.refresh_ui, "filler_capacitance_over_area")

        self.refresh_ui()

    @observe("model:[liquid_capacitance_over_area, filler_capacitance_over_area]")
    def refresh_ui(self, event=None):
        l_val = self.model.liquid_capacitance_over_area
        f_val = self.model.filler_capacitance_over_area

        l_text = f"C_l: {l_val:.4f} pF/mm²" if self.model.liquid_capacitance_over_area is not None else "C_l: -"
        f_text = f"C_f: {f_val:.4f} pF/mm²" if self.model.filler_capacitance_over_area is not None else "C_f: -"

        self.view.display_values(l_text, f_text)


if __name__ == "__main__":
    from pyface.qt.QtGui import QApplication
    import sys

    from pathlib import Path
    from examples.tests.common import TEST_PATH
    from microdrop_style.helpers import style_app, get_complete_stylesheet, is_dark_mode
    from device_viewer.models.electrodes import Electrodes


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
        