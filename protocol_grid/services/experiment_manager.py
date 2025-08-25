import os
import sys
import shutil
import subprocess
import json
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication

from microdrop_utils._logger import get_logger

logger = get_logger(__name__)


class ExperimentManager:
    """manage experiment lifecycle, directory creation, and cleanup."""
    
    def __init__(self):
        self._experiment_id = None
        self._experiment_directory = None
        self._base_experiments_dir = None
        self._initialized = False
        
    def initialize(self):
        """initialize self and create experiment directory."""
        if self._initialized:
            return
            
        try:
            # create base directory: experiment_logs
            self._base_experiments_dir = self._get_base_experiments_directory()
            self._base_experiments_dir.mkdir(parents=True, exist_ok=True)
            
            # generate unique experiment ID
            self._experiment_id = self._generate_experiment_id()
            
            # create directory
            #TODO: change this to a more appropriate location (System Documents) after dev
            self._experiment_directory = self._base_experiments_dir / self._experiment_id
            self._experiment_directory.mkdir(parents=True, exist_ok=True)
            
            self._register_cleanup_on_exit() # on app exit
            
            self._initialized = True
            logger.info(f"Experiment initialized: {self._experiment_id}")
            
        except Exception as e:
            logger.error(f"Failed to initialize experiment: {e}")
            # fallback to current directory
            self._experiment_directory = Path.cwd()
            self._experiment_id = "fallback"
            self._initialized = True
    
    def _get_base_experiments_directory(self):
        # find Microdrop root directory by looking for the script file
        #TODO: this assumes the script is always located in a known path relative to the Microdrop root.
        # change this logic if/when the structure changes.
        current_file = Path(__file__)
        microdrop_root = None
        
        # walk up to find Microdrop root
        for parent in current_file.parents:
            if (parent / "examples" / "run_device_viewer_pluggable.py").exists():
                microdrop_root = parent
                break
        
        if not microdrop_root:
            # fallback: assuming this file is located in Microdrop/protocol_grid/services/
            #TODO: check if this is correct before deployment
            microdrop_root = current_file.parents[2]
            
        return microdrop_root / "experiment_logs"
    
    def _generate_experiment_id(self):
        timestamp = datetime.now()
        return timestamp.strftime("%Y_%m_%d_%H_%M_%S")
    
    def _register_cleanup_on_exit(self):
        """cleanup function to run when application exits."""
        app_instance = QApplication.instance() or QApplication(sys.argv)
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
                logger.info(f"Cleaned up empty experiment directory: {self._experiment_id}")
            else:
                logger.info(f"Experiment directory not empty, keeping: {self._experiment_id}")
        except Exception as e:
            logger.error(f"Failed to cleanup experiment directory: {e}")
    
    def _is_directory_empty(self, directory):
        """check if directory is completely empty."""
        try:
            return len(list(directory.iterdir())) == 0
        except Exception:
            return False
    
    def get_experiment_id(self):
        if not self._initialized:
            self.initialize()
        return self._experiment_id or "unknown"
    
    def get_experiment_directory(self):
        if not self._initialized:
            self.initialize()
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
    
    def cleanup_experiment_jsons(self):
        """delete all JSON files in the current experiment directory."""
        try:
            experiment_dir = self.get_experiment_directory()
            
            # find and delete all .json files
            json_files = list(experiment_dir.glob("*.json"))
            for json_file in json_files:
                json_file.unlink()
                logger.info(f"Deleted existing JSON file: {json_file.name}")
                
        except Exception as e:
            logger.error(f"Failed to cleanup experiment JSONs: {e}")
    
    def auto_save_protocol(self, protocol_data, protocol_name=None, is_modified=False):
        """auto-save protocol to experiment directory with standard filename."""
        try:
            # cleanup existing JSONs first
            self.cleanup_experiment_jsons()
            
            # create filename
            if protocol_name and protocol_name != "untitled" and not is_modified:
                # use current protocol name if not modified
                filename = f"{protocol_name}.json"
            else:
                # use experiment ID if untitled or modified
                filename = f"protocol_{self._experiment_id}.json"
            file_path = self.get_experiment_directory() / filename
            
            # save protocol
            with open(file_path, "w") as f:
                json.dump(protocol_data, f, indent=2)
            
            logger.info(f"Auto-saved protocol to: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"Failed to auto-save protocol: {e}")
            return None 
    
    def initialize_new_experiment(self):
        """initialize a new experiment with new ID and directory."""
        try:
            # generate new experiment ID
            self._experiment_id = self._generate_experiment_id()
            
            # create new experiment directory
            self._experiment_directory = self._base_experiments_dir / self._experiment_id
            self._experiment_directory.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Initialized new experiment: {self._experiment_id}")
            return self._experiment_id
            
        except Exception as e:
            logger.error(f"Failed to initialize new experiment: {e}")
            return None