import json

from traits.api import Bool, Instance

from microdrop_utils.decorators import timestamped_value
from portable_dropbot_controller.consts import (
    FLUORESCENCE_LED_RAW_MAX, LIGHT_INTENSITY_RAW_MAX,
)
from template_status_and_controls.base_message_handler import (
    BaseMessageHandler,
)

from ..consts import RGY_STATE_NAMES
from ..models.temp_lighting_model import PortableDropbotTempLightingModel


class PortableDropbotTempLightingMessageHandler(BaseMessageHandler):
    """Connection greying (inherited), the TEMP_UPDATED stream
    (per-channel readings and PID readbacks), and a one-shot seed of
    the lighting controls from the board's own reported state."""

    model = Instance(PortableDropbotTempLightingModel)

    #: The lighting controls were seeded from a status snapshot this
    #: connection; reset on every connect so a reconnect re-seeds.
    _lighting_seeded = Bool(False)

    @timestamped_value("connected_message")
    def _on_connected_triggered(self, body):
        self.model.connected = True
        self._lighting_seeded = False

    def _on_status_updated_triggered(self, body):
        """Seed the lighting controls once per connection from the
        first snapshot, so the pane opens on what the board is
        actually doing instead of the trait defaults. One-shot on
        purpose: a continuous sync would fight the user's own edits
        every poll (and the status units are lossy — % and ‰ of the
        raw setpoints)."""
        if self._lighting_seeded:
            return
        data = json.loads(str(body))
        self.model.seeding = True
        try:
            rgy_state = data.get("rgy_state")
            if rgy_state in RGY_STATE_NAMES:
                self.model.rgb_light = RGY_STATE_NAMES[rgy_state]
            illumination_pct = data.get("light_led_bright")
            if illumination_pct is not None:
                self.model.illumination_raw = min(
                    LIGHT_INTENSITY_RAW_MAX,
                    round(illumination_pct
                          * LIGHT_INTENSITY_RAW_MAX / 100))
            flu_permille = data.get("flu_led_bright")
            if flu_permille is not None:
                self.model.fluorescence_led_raw = min(
                    FLUORESCENCE_LED_RAW_MAX,
                    round(flu_permille
                          * FLUORESCENCE_LED_RAW_MAX / 1000))
        finally:
            self.model.seeding = False
        self._lighting_seeded = True

    def _on_temp_updated_triggered(self, body):
        data = json.loads(str(body))
        channel = data.get("channel")
        if "pid" in data:
            if channel == self.model.temp_channel:
                pid = data["pid"]
                self.model.pid_kp = float(pid["kp"])
                self.model.pid_ki = float(pid["ki"])
                self.model.pid_kd = float(pid["kd"])
                self.model.pid_period_ms = int(pid["period_ms"])
            return
        if "current_c" in data:
            self.model.temp_info_display = (
                f"ch{channel}: {data['current_c']:.2f} °C "
                f"(target {data['target_c']:.2f} °C, "
                f"output {data['output_pct']:.1f} %)")
