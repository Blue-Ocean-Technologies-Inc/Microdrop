# sys imports

from pathlib import Path

from dramatiq import get_broker
from traits.etsconfig.api import ETSConfig

from microdrop_utils.redis_manager import get_redis_hash_proxy
from .helpers import sync_redis_globals
# Local imports.
from .preferences import MicrodropPreferences

# Enthought library imports.
from envisage.api import Application
from traits.api import Instance, Property, Directory

from .consts import EXPERIMENT_DIR, APP_GLOBALS_REDIS_HASH

from logger.logger_service import get_logger
logger = get_logger(__name__)


# set some global consts used application wide.
ETSConfig.company = "Sci-Bots"
ETSConfig.user_data = str(Path.home() / "Documents" / ETSConfig.company / "Microdrop")
ETSConfig.application_home = str(Path(ETSConfig.application_data) / "Microdrop")


class MicrodropBackendApplication(Application):
    """Device Viewer application based on enthought envisage's The chaotic attractors Tasks application."""

    #### 'IApplication' interface #############################################

    # The application's globally unique identifier.
    id = "microdrop_backend.app"

    # The application's user-visible name.
    name = "Microdrop Next Gen Backend"

    # experiments directory
    experiments_directory = Property(Directory)
    current_experiment_directory = Property(Directory)

    #### 'Application' interface ####################################

    preferences_helper = Instance(MicrodropPreferences)

    def _preferences_helper_default(self):
        """
        Retrieve the preferences from the preferences file using the DeviceViewerPreferences class.
        """
        return MicrodropPreferences(preferences=self.preferences)

    def _get_experiments_directory(self) -> Path:
        return Path(self.preferences_helper.EXPERIMENTS_DIR)

    def _get_current_experiment_directory(self) -> Path:
        # try to get experiment directory from app globals
        exp_dir = sync_redis_globals(key="experiment_directory", set_value=EXPERIMENT_DIR)

        return self.experiments_directory / exp_dir

    ############################# Initialization ############################################################
    def traits_init(self):
        self.current_experiment_directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized microdrop application. Current experiment directory: {self.current_experiment_directory}")