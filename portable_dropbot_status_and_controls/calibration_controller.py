from traits.api import observe
from traitsui.api import Controller

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import (
    READ_CAL_CAPS, READ_ELECTRODE_GAIN, RUN_CAP_CALIBRATION,
    SET_CAL_CAPS, SET_ELECTRODE_GAIN, SET_ML_REALTIME,
)

logger = get_logger(__name__)


class CalibrationController(Controller):
    """Buttons -> request topics; the results come back through the
    message handler on CALIBRATION_UPDATED."""

    @observe("model:run_calibration_button")
    def _run_calibration(self, event):
        self.model.calibration_status = "running..."
        logger.info("Requested ML calibration macro")
        publish_message(topic=RUN_CAP_CALIBRATION, message="")

    @observe("model:ml_realtime")
    def _on_ml_realtime_changed(self, event):
        publish_message(topic=SET_ML_REALTIME,
                        message=str(bool(event.new)))

    @observe("model:read_gain_button")
    def _read_gain(self, event):
        publish_message(topic=READ_ELECTRODE_GAIN, message="")

    @observe("model:apply_gain_button")
    def _apply_gain(self, event):
        publish_message(topic=SET_ELECTRODE_GAIN,
                        message=str(int(self.model.electrode_gain)))

    @observe("model:read_cal_caps_button")
    def _read_cal_caps(self, event):
        publish_message(topic=READ_CAL_CAPS, message="")

    @observe("model:apply_cal_caps_button")
    def _apply_cal_caps(self, event):
        publish_message(topic=SET_CAL_CAPS,
                        message=str(int(self.model.cal_caps)))
