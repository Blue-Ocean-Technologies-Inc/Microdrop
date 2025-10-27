import json

from traits.api import provides, HasTraits, Str
from traits.has_traits import observe

from logger.logger_service import get_logger
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from ..interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService
logger = get_logger(__name__, "DEBUG")

@provides(IDropbotControlMixinService)
class DropbotChangeSettingsService(HasTraits):
    """
    A mixin Class that adds methods to monitor a dropbot connection and get some dropbot information.
    """

    id = Str("dropbot_settings_change")
    name = Str('Dropbot Settings Change')

    ######################################## Methods to Expose #############################################
    def on_change_settings_request(self, message):
        logger.critical(f"Processing a change dropbot settings request: {message}")
        new_traits = json.loads(message)
        self.preferences.trait_set(**new_traits)

    @observe('preferences:capacitance_update_interval')
    def _capacitance_update_interval_changed(self, event):
        logger.debug(f"Received capacitance update event: {event}")

        if self.proxy is not None:
            if self.proxy.monitor is not None:
                with self.proxy.transaction_lock:
                    current_update_interval = self.proxy.state["capacitance_update_interval_ms"]
                    if event.new != current_update_interval:
                        self.proxy.update_state(capacitance_update_interval_ms=int(event.new))
                        logger.critical(f"Changed capacitance update interval to {event.new} from {current_update_interval} ms")
                    else:
                        logger.warning(f"No change in capacitance update interval. Current value is already {event.new}.")

                    return

        logger.warning(f"Proxy connection Missing. {event.name.title()} request Denied.")

    @observe('preferences:[capacitance_update_interval, droplet_detection_capacitance]')
    def _preference_changed(self, event):
        logger.debug(f"Received preferences change event: {event}")

        app_globals = get_microdrop_redis_globals_manager()
        app_globals[event.name] = event.new