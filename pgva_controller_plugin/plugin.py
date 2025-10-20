"""
PGVA Controller Plugin
Integrates the Festo PGVA pressure/vacuum generator controller into the Microdrop application.
"""

from traits.api import Instance
from envisage.api import Plugin

from .consts import PKG, PKG_name
from .pgva_controller_base import PGVAControllerBase
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)


class PGVAControllerPlugin(Plugin):
    """
    Plugin for controlling Festo PGVA pressure/vacuum generator via ethernet.
    """
    
    # Plugin metadata
    id = f"{PKG}.plugin"
    name = PKG_name
    
    # Controller instance
    pgva_controller = Instance(PGVAControllerBase)
    
    def _pgva_controller_default(self):
        """Create default PGVA controller instance."""
        return PGVAControllerBase()
    
    def start(self):
        """Start the plugin."""
        logger.info(f"Starting {self.name} plugin")
        
        # Initialize the controller
        if self.pgva_controller:
            logger.info("PGVA controller initialized")
        else:
            logger.error("Failed to initialize PGVA controller")
    
    def stop(self):
        """Stop the plugin."""
        logger.info(f"Stopping {self.name} plugin")
        
        # Cleanup controller resources
        if self.pgva_controller:
            self.pgva_controller.cleanup()
            logger.info("PGVA controller cleaned up")
    
    def get_controller(self):
        """
        Get the PGVA controller instance.
        
        Returns:
            PGVAControllerBase: The controller instance
        """
        return self.pgva_controller
    
    def get_listener(self):
        """
        Get the PGVA controller's listener for message handling.
        
        Returns:
            The controller instance (which implements the listener interface)
        """
        return self.pgva_controller
