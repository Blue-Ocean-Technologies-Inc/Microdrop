import json

from traits.api import observe

from microdrop_utils.decorators import debounce
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from template_status_and_controls.base_controller import BaseStatusController

from .consts import (
    MOCK_CHANGE_SIM_SETTINGS, MOCK_SIMULATE_CHIP_INSERT,
    MOCK_SIMULATE_SHORTS, MOCK_SIMULATE_HALT,
)

from logger.logger_service import get_logger

logger = get_logger(__name__)


class MockDropbotDockPaneController(BaseStatusController):
    """Controller for the MockDropBot dock pane.

    Communicates with the mock backend exclusively via pub/sub topics.
    """

    # ---- Debounced setattr for sliders ----

    @debounce(wait_seconds=0.3)
    def base_capacitance_pf_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @debounce(wait_seconds=0.3)
    def capacitance_delta_pf_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @debounce(wait_seconds=0.3)
    def capacitance_noise_pf_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @debounce(wait_seconds=0.3)
    def stream_interval_ms_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    # ---- Observers: publish simulation setting changes to backend ----

    @observe("model:base_capacitance_pf")
    def _on_base_cap_changed(self, event):
        publish_message(
            topic=MOCK_CHANGE_SIM_SETTINGS,
            message=json.dumps({"base_capacitance_pf": event.new}),
        )

    @observe("model:capacitance_delta_pf")
    def _on_delta_cap_changed(self, event):
        publish_message(
            topic=MOCK_CHANGE_SIM_SETTINGS,
            message=json.dumps({"capacitance_delta_pf": event.new}),
        )

    @observe("model:capacitance_noise_pf")
    def _on_noise_cap_changed(self, event):
        publish_message(
            topic=MOCK_CHANGE_SIM_SETTINGS,
            message=json.dumps({"capacitance_noise_pf": event.new}),
        )

    @observe("model:stream_interval_ms")
    def _on_interval_changed(self, event):
        publish_message(
            topic=MOCK_CHANGE_SIM_SETTINGS,
            message=json.dumps({"stream_interval_ms": event.new}),
        )

    # ---- Button handlers: publish simulation events to backend ----

    @observe("model:simulate_shorts_button")
    def _on_simulate_shorts(self, event):
        text = self.model.shorts_channels_text.strip()
        try:
            channels = [int(ch.strip()) for ch in text.split(",") if ch.strip()]
        except ValueError:
            logger.error(f"Invalid shorts channels: '{text}'. Use comma-separated integers.")
            return
        publish_message(topic=MOCK_SIMULATE_SHORTS, message=json.dumps(channels))
        logger.info(f"Published simulate shorts: {channels}")

    @observe("model:simulate_halt_button")
    def _on_simulate_halt(self, event):
        publish_message(topic=MOCK_SIMULATE_HALT, message=self.model.halt_error_type)
        logger.info(f"Published simulate halt: {self.model.halt_error_type}")

    @observe("model:simulate_chip_toggle")
    def _on_simulate_chip_toggle(self, event):
        # Toggle: if currently inserted, remove; otherwise insert
        currently_inserted = self.model.chip_inserted
        publish_message(topic=MOCK_SIMULATE_CHIP_INSERT, message=str(not currently_inserted))
        logger.info(f"Published simulate chip: {not currently_inserted}")
