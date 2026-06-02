from traits.api import HasTraits, Float, Instance, observe

from device_viewer.models.electrodes import Electrodes

from logger.logger_service import get_logger
logger = get_logger(__name__)

from microdrop_application.helpers import get_microdrop_redis_globals_manager
app_globals = get_microdrop_redis_globals_manager()


def _update_app_globals_on_trait_change_event(event, value_units=""):
    app_globals[event.name] = event.new
    logger.info(f"App Globals Update: {event.name}: {event.new} {value_units}")


class CalibrationModel(HasTraits):

    last_capacitance = Float(desc="last capacitance reported by dropbot in pF")  # pF

    liquid_capacitance_over_area = Float(allow_none=True, default_value=None, desc="Measure capacitance in selected electrodes covered by liquid normalized over electrode area in pF/mm^2")
    filler_capacitance_over_area = Float(allow_none=True, default_value=None, desc="Measure capacitance in selected electrodes covered by air normalized over electrode area in pF/mm^2")

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
        self.reset_traits(["filler_capacitance_over_area", "liquid_capacitance_over_area"])

    @observe("liquid_capacitance_over_area")
    def _liquid_capacitance_changed(self, event):
        _update_app_globals_on_trait_change_event(event, "pF/mm^2")

    @observe("filler_capacitance_over_area")
    def _filler_capacitance_changed(self, event):
        _update_app_globals_on_trait_change_event(event,"pF/mm^2")

