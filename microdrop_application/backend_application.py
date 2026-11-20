# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from envisage.api import Application
from traits.api import Directory, Event, Instance, Property

# Microdrop utils imports.
from microdrop_utils.application_home import configure_application_home

# Local imports.
from .consts import EXPERIMENT_DIR
from .helpers import get_microdrop_redis_globals_manager
from .preferences import MicrodropPreferences

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


configure_application_home()


class MicrodropBackendApplication(Application):
    """The MicroDrop backend Envisage application, without a GUI."""

    #### 'IApplication' interface #############################################

    # The application's globally unique identifier.
    id = "microdrop.backend.app"

    # The application's user-visible name.
    name = "Microdrop Next Gen Backend"

    # experiments directory
    experiments_directory = Property(Directory)
    current_experiment_directory = Property(Directory)
    experiment_changed = Event()

    #### 'Application' interface ####################################

    preferences_helper = Instance(MicrodropPreferences)

    def _preferences_helper_default(self):
        """Wrap the application preferences in the MicroDrop preferences helper."""
        return MicrodropPreferences(preferences=self.preferences)

    def _get_experiments_directory(self) -> Path:
        return Path(self.preferences_helper.EXPERIMENTS_DIR)

    def _get_current_experiment_directory(self) -> Path:
        # try to get experiment directory from app globals
        globals = get_microdrop_redis_globals_manager()

        current_exp_dir = globals.get("experiment_directory", None)

        if current_exp_dir is None:
            current_exp_dir = EXPERIMENT_DIR
            globals["experiment_directory"] = EXPERIMENT_DIR

        return self.experiments_directory / current_exp_dir

    def _set_current_experiment_directory(self, directory: Path):
        if not isinstance(directory, Path):
            directory = Path(directory)

        globals = get_microdrop_redis_globals_manager()
        globals["experiment_directory"] = directory.stem

        self._get_current_experiment_directory().mkdir(parents=True, exist_ok=True)

        self.experiment_changed = True

    #### Initialization #######################################################
    def traits_init(self):
        self.current_experiment_directory.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"Initialized microdrop application. Current experiment directory: "
            f"{self.current_experiment_directory}"
        )
