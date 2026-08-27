# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from traits.api import HasTraits, Str, provides

from logger.logger_service import get_logger

from ..consts import (
    FLUORESCENCE_LED_RAW_MAX,
    LIGHT_INTENSITY_RAW_MAX,
    RGB_LIGHT_STATES,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotStatesSettingMixinService(HasTraits):
    id = Str("portable_dropbot_states_setting_mixin_service")
    name = Str("Portable Dropbot States Setting Mixin")

    def on_set_realtime_mode_request(self, message):
        self.realtime_mode = str(message) == "True"
        self._publish_realtime_mode()

        # The vendor UI's HV On/Off follows realtime mode here: HV
        # only energizes while realtime is on (pad-interlocked, no
        # bypass — the firmware still refuses without a device on the
        # pads), and leaving realtime kills it.
        if self.realtime_mode:
            ok, status = self._proxy_call(
                "HV enable", lambda: self.proxy.uart.hv_enable(1, 0)
            )
        else:
            # Leaving realtime mode releases every electrode, exactly
            # as the other backends do — then de-energizes HV.
            self._proxy_call("clear channels", lambda: self.proxy.clear_channels())
            ok, status = self._proxy_call(
                "HV disable", lambda: self.proxy.uart.hv_enable(0, 0)
            )

        logger.info(
            f"Portable Dropbot realtime mode set to "
            f"{self.realtime_mode}; HV "
            f"{'enable' if self.realtime_mode else 'disable'} "
            f"--> {'ok' if ok and status is not None else 'FAILED'}"
        )

    def on_set_voltage_request(self, message):
        self.voltage = int(float(str(message)))
        self._apply_actuation()
        logger.info(f"Portable Dropbot voltage set to {self.voltage} V")

    def on_set_frequency_request(self, message):
        self.frequency = int(float(str(message)))
        self._apply_actuation()
        logger.info(f"Portable Dropbot frequency set to {self.frequency} Hz")

    def on_set_light_intensity_request(self, message):
        self.light_intensity = int(float(str(message)))
        self._apply_light_intensity()

        if self.preferences is not None:
            # Persisted as the next connect's default, as before.
            self.preferences.default_light_intensity = self.light_intensity

        logger.info(f"Portable Dropbot light intensity set to {self.light_intensity} %")

    def on_set_light_on_request(self, message):
        self.light_on = str(message) == "True"
        self._apply_light_intensity()
        logger.info(f"Portable Dropbot illumination {'on' if self.light_on else 'off'}")

    def on_set_rgb_light_request(self, message):
        color = str(message).strip().lower()
        if color not in RGB_LIGHT_STATES:
            logger.warning(f"Unknown RGB light state: {color!r}")
            return

        ok, result = self._proxy_call(
            f"rgb light {color}", lambda: self.proxy.uart.setBoxLight(color)
        )
        logger.info(
            f"Portable Dropbot RGB light --> {color}: "
            f"{'ok' if ok and result else 'FAILED'}"
        )

    def on_set_illumination_raw_request(self, message):
        """Vendor-style raw illumination brightness, 0-255 straight
        to the firmware — no % scaling."""
        raw = min(max(0, int(float(str(message)))), LIGHT_INTENSITY_RAW_MAX)
        ok, result = self._proxy_call(
            f"illumination raw {raw}",
            lambda: self.proxy.uart.setLEDIntensity(raw, fluorescence=False),
        )
        logger.info(
            f"Portable Dropbot illumination raw --> {raw}: "
            f"{'ok' if ok and result else 'FAILED'}"
        )

    def on_set_fluorescence_led_raw_request(self, message):
        """Vendor-style raw fluorescence LED brightness, 16-bit
        0-65535 straight to the firmware."""
        raw = min(max(0, int(float(str(message)))), FLUORESCENCE_LED_RAW_MAX)
        ok, result = self._proxy_call(
            f"fluorescence LED raw {raw}",
            lambda: self.proxy.uart.setLEDIntensity(raw, fluorescence=True),
        )
        logger.info(
            f"Portable Dropbot fluorescence LED raw --> {raw}: "
            f"{'ok' if ok and result else 'FAILED'}"
        )
