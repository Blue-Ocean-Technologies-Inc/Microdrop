import json

from traits.api import Instance

from microdrop_utils.decorators import timestamped_value
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import (
    READ_CAL_CAPS, READ_ELECTRODE_GAIN,
)
from template_status_and_controls.base_message_handler import (
    BaseMessageHandler,
)

from ..models.calibration_model import PortableDropbotCalibrationModel


class PortableDropbotCalibrationMessageHandler(BaseMessageHandler):
    """Connection greying (inherited) plus the CALIBRATION_UPDATED
    stream: macro stage progress and the gain / cal-caps / ML-path
    readbacks."""

    model = Instance(PortableDropbotCalibrationModel)

    @timestamped_value("connected_message")
    def _on_connected_triggered(self, body):
        self.model.connected = True
        # Pull the board's persisted provisioning so the pane shows
        # reality, not the trait defaults.
        publish_message(topic=READ_ELECTRODE_GAIN, message="")
        publish_message(topic=READ_CAL_CAPS, message="")

    def _on_calibration_updated_triggered(self, body):
        data = json.loads(str(body))
        if "stage" in data:
            if data["stage"] == "done":
                self.model.calibration_status = (
                    "Calibration complete" if data.get("ok")
                    else "Calibration FAILED — see log")
            else:
                outcome = "ok" if data.get("ok") else "FAILED"
                self.model.calibration_status = \
                    f"{data['stage']} — {outcome}"
        if "electrode_gain" in data:
            self.model.electrode_gain = int(data["electrode_gain"])
        if data.get("cal_caps") in (3, 5):
            self.model.cal_caps = int(data["cal_caps"])
        if "ml_realtime" in data:
            self.model.ml_realtime = bool(data["ml_realtime"])
