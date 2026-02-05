from envisage.plugin import Plugin

# microdrop imports
from logger.logger_service import get_logger
# Initialize logger
logger = get_logger(__name__)

from .consts import PKG, PKG_name

class PortDropbotControllerPlugin(Plugin):
    id = PKG + ".plugin"
    name = PKG_name


    def start(self):
        """Initialize the dropbot on plugin start"""

        from .manager import ConnectionManager

        self.dropbot_controller = ConnectionManager()

        self.dropbot_controller.on_start_device_monitoring_request()

    def stop(self):
        """Cleanup when the plugin is stopped."""
        if hasattr(self, "dropbot_controller"):
            self.dropbot_controller.driver.close()