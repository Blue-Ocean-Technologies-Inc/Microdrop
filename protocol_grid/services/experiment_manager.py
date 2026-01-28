import sys
import shutil
import subprocess
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication

from logger.logger_service import get_logger
from microdrop_utils.datetime_helpers import get_current_utc_datetime

logger = get_logger(__name__)


class ExperimentManager:
    """manage experiment lifecycle, directory creation, and cleanup."""
    
    def __init__(self, experiment_directory: Path):
        self._initialized = False
        self._experiment_directory = experiment_directory
        self._register_cleanup_on_exit() # on app exit
        logger.info(f"Experiment initialized: Directory={self._experiment_directory}")
    
    def _register_cleanup_on_exit(self):
        """cleanup function to run when application exits."""
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self._cleanup_on_exit)
    
    def _cleanup_on_exit(self):
        """cleanup experiment directory if empty on application exit."""
        if not self._experiment_directory or not self._experiment_directory.exists():
            return
            
        try:
            if self._is_directory_empty(self._experiment_directory):
                shutil.rmtree(self._experiment_directory)
                logger.info(f"Cleaned up empty experiment directory: {self._experiment_directory}")
            else:
                logger.info(f"Experiment directory not empty, keeping: {self._experiment_directory}")
        except Exception as e:
            logger.error(f"Failed to cleanup experiment directory: {e}")
    
    def _is_directory_empty(self, directory):
        """check if directory is completely empty."""
        try:
            return len(list(directory.iterdir())) == 0
        except Exception:
            return False

    def get_experiment_directory(self):
        return self._experiment_directory or Path.cwd()
    
    def open_experiment_directory(self):
        """open experiment directory in file explorer."""
        directory = self.get_experiment_directory()
        if directory.exists():            
            try:
                if sys.platform.startswith("win"):
                    subprocess.run(["explorer", str(directory)])
                elif sys.platform == "darwin":
                    subprocess.run(["open", str(directory)])
                else:  # linux and others
                    subprocess.run(["xdg-open", str(directory)])
            except Exception as e:
                logger.error(f"Failed to open experiment directory: {e}")
    
    def is_save_in_experiment_directory(self, file_path):
        """check if the file path is exactly in the current experiment directory."""
        try:
            file_path = Path(file_path)
            experiment_dir = self.get_experiment_directory()
            
            return file_path.parent.resolve() == experiment_dir.resolve()
        except Exception as e:
            logger.error(f"Error checking if save is in experiment directory: {e}")
            return False

    def auto_save_protocol(self, protocol_data) -> Path | None:
        """auto-save protocol to experiment directory with standard filename."""
        try:
            parent_dir = self.get_experiment_directory() / "protocols"
            parent_dir.mkdir(parents=True, exist_ok=True)
            file_path = parent_dir / f"protocol_{get_current_utc_datetime()}.json"

            # save protocol
            with open(file_path, "w") as f:
                json.dump(protocol_data, f, indent=2)

            logger.info(f"Auto-saved protocol to: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Failed to auto-save protocol: {e}")
            return None

    def initialize_new_experiment(self):
        """initialize a new experiment with new ID and directory."""
        try:
            # generate new experiment ID
            new_experiment_dir = get_current_utc_datetime()

            # create new experiment directory
            _experiment_directory = self._experiment_directory.parent / new_experiment_dir
            _experiment_directory.mkdir(parents=True, exist_ok=True)

            logger.info(f"Initialized new experiment: {_experiment_directory}")
            self._experiment_directory = _experiment_directory

            return self._experiment_directory

        except Exception as e:
            logger.error(f"Failed to initialize new experiment: {e}")
            return None