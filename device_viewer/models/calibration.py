from traits.api import HasTraits, Float, Instance

from device_viewer.models.electrodes import Electrodes
from device_viewer.models.main_model import logger


class CalibrationModel(HasTraits):

    last_capacitance = Float(desc="last capacitance reported by dropbot in pF")  # pF

    liquid_capacitance_over_area = Float(allow_none=True, desc="Measure capacitance in selected electrodes covered by liquid normalized over electrode area in pF/mm^2")
    filler_capacitance_over_area = Float(allow_none=True, desc="Measure capacitance in selected electrodes covered by air normalized over electrode area in pF/mm^2")

    # Reference to electrodes for area calculations
    electrodes = Instance(Electrodes)

    def measure_filler_capacitance(self):
        area = self.electrodes.get_activated_electrode_area_mm2()
        if not self.electrodes.any_electrode_on() or area == 0:
            logger.warning("Cannot measure filler: No electrodes active.")
            return

        if self.last_capacitance:
            self.filler_capacitance_over_area = self.last_capacitance / area

    def measure_liquid_capacitance(self):
        area = self.electrodes.get_activated_electrode_area_mm2()
        if not self.electrodes.any_electrode_on() or area == 0:
            logger.warning("Cannot measure liquid: No electrodes active.")
            return

        if self.last_capacitance:
            self.liquid_capacitance_over_area = self.last_capacitance / area

    def reset(self):
        self.liquid_capacitance_over_area = None
        self.filler_capacitance_over_area = None
