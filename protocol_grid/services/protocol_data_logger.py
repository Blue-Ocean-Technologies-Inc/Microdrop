import json
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from device_viewer.models.media_capture_model import MediaCaptureMessageModel, MediaType
from logger.logger_service import get_logger
from microdrop_utils.datetime_helpers import (
    TimestampedMessage,
    get_current_utc_datetime,
    get_elapsed_time_from_utc_datetime,
)
from microdrop_utils.sticky_notes import StickyWindowManager

logger = get_logger(__name__)

class ProtocolDataLogger:
    """Service for logging capacitance data during protocol execution."""

    def __init__(self, protocol_widget=None):
        self.parent = protocol_widget
        self._metadata_entries = {}
        self._data_entries = []
        self._data_files = []
        self._video_captures = []
        self._image_captures = []
        self._other_media_captures = []
        self.last_saved_summary_path = None

        self._is_logging_active = False
        self._latest_capacitance_per_unit_area = None
        self._current_protocol_context = None
        self._experiment_directory = None
        self._preview_mode = False

        self._columns = []

    def start_logging(
        self,
        experiment_directory: Path,
        preview_mode: bool = False,
        n_steps: int = 1,
    ):

        if preview_mode:
            logger.info("Skipping data logging in preview mode")
            self._is_logging_active = False
            return

        # clear data
        self._data_entries.clear()
        self._data_files.clear()
        self._video_captures.clear()
        self._image_captures.clear()
        self._other_media_captures.clear()

        # set flags
        self._is_logging_active = True
        self._preview_mode = preview_mode

        # set metadata
        self._experiment_directory = experiment_directory
        self._total_nsteps = n_steps
        _start_timestamp = get_current_utc_datetime()

        self.log_metadata(
            {
                "Experiment Directory": f'<a href="file:///{self._experiment_directory}">{Path(self._experiment_directory).name}</a>',
                "Steps Completed": f"0 / {self._total_nsteps}",
                "Start Time": _start_timestamp,
            }
        )

        logger.info(f"Started protocol data logging to: {experiment_directory}")

    def stop_logging(self, completed_steps=None):
        if completed_steps:
            _completed_nsteps = completed_steps
        else:
            _completed_nsteps = self._total_nsteps

        self.log_metadata({"Steps Completed": f"{_completed_nsteps} / {self._total_nsteps}"})

        self._is_logging_active = False
        logger.info("Stopped protocol data logging")

        _stop_timestamp = get_current_utc_datetime()
        _start_timestamp = self._metadata_entries.get("Start Time")
        _elapsed_time = get_elapsed_time_from_utc_datetime(_start_timestamp, _stop_timestamp)

        self.log_metadata({"Stop Time": _stop_timestamp,
                           "Elapsed Time": _elapsed_time})

    def set_protocol_context(self, context: Dict):
        self._current_protocol_context = context

    def update_capacitance_per_unit_area(self, c_unit_area: float):
        self._latest_capacitance_per_unit_area = c_unit_area
        logger.debug(f"Updated capacitance per unit area: {c_unit_area}")

    def log_media_capture(self, message: MediaCaptureMessageModel):
        if message.type == MediaType.VIDEO:
            self._video_captures.append(message.path)
        elif message.type == MediaType.IMAGE:
            self._image_captures.append(message.path)
        elif message.type == MediaType.OTHER:
            self._other_media_captures.append(message.path)

    def log_data(self, data_point:dict):
        # Automatically add a timestamp if it's missing
        if "utc_time" not in data_point:
            data_point["utc_time"] = get_current_utc_datetime()

        self._data_entries.append(data_point)

        # Automatically keep track of columns seen so far
        for key in data_point.keys():
            if key not in self._columns:
                self._columns.append(key)
    
    def log_metadata(self, data_point:dict):
        self._metadata_entries.update(data_point)

    def log_capacitance_data(self, capacitance_message: TimestampedMessage):
        if not self._is_logging_active or self._preview_mode:
            return

        try:
            # parse capacitance message
            capacitance_data = json.loads(capacitance_message)
            capacitance_str = capacitance_data.get("capacitance", "-")
            voltage_str = capacitance_data.get("voltage", "-")
            timestamp = capacitance_message.timestamp

            if capacitance_str == "-" or voltage_str == "-":
                logger.debug("Invalid capacitance/voltage data, skipping log entry")
                return

            # extract numeric values - handle both "pF" and " pF" formats
            try:
                if "pF" in capacitance_str:
                    capacitance_value = float(capacitance_str.replace("pF", "").strip())
                else:
                    capacitance_value = float(capacitance_str)
            except ValueError:
                logger.debug(f"Could not parse capacitance value: {capacitance_str}")
                return

            try:
                if "V" in voltage_str:
                    voltage_value = float(voltage_str.replace("V", "").strip())
                else:
                    voltage_value = float(voltage_str)
            except ValueError:
                logger.debug(f"Could not parse voltage value: {voltage_str}")
                return

            # get current protocol context
            if not self._current_protocol_context:
                logger.debug("No protocol context available, skipping log entry")
                return

            step_id = self._current_protocol_context.get("step_id", "")
            step_idx = self._current_protocol_context.get("step_idx", "")
            actuated_channels = self._current_protocol_context.get(
                "actuated_channels", []
            )
            actuated_area = self._current_protocol_context.get("actuated_area", 0)

            # calculate force
            force = self._calculate_force(voltage_value)

            data_entry = {
                "utc_time": timestamp,
                "step_id": step_id,
                "step_idx": step_idx,
                "Capacitance (pF)": capacitance_value,
                "Voltage (V)": voltage_value,
                "Force Over Unit Area (mN/mm^2)": force,
                "Actuated Area (mm^2)": actuated_area,
                "actuated_channels": actuated_channels,
            }

            self.log_data(data_entry)

            logger.debug(
                f"Logged data entry: step={step_id}, channels={len(actuated_channels)}, force={force}"
            )

        except Exception as e:
            logger.error(
                f"Error logging capacitance data: {e}. message: {capacitance_message}"
            )

    def _calculate_force(self, voltage: float) -> Optional[float]:
        if self._latest_capacitance_per_unit_area is None or voltage <= 0:
            return None

        try:
            # force = 0.5 x capacitance_per_unit_area x voltage^2
            force = 0.5 * self._latest_capacitance_per_unit_area * (voltage**2)
            return round(force, 6)
        except Exception as e:
            logger.error(f"Error calculating force: {e}")
            return None

    def _convert_to_columnar_format(self) -> Dict:
        """Convert list of entry dictionaries to columnar format with single start timestamp."""
        if not self._data_entries:
            return {
                "start_timestamp": None,
                "columns": self._columns,
                "data": [[] for _ in self._columns],
            }

        columnar_data = {col: [] for col in self._columns}

        for entry in self._data_entries:
            for col in self._columns:
                value = entry.get(col)
                if value is None:
                    if col in [
                        "force_per_unit_area",
                        "actuated_area_mm2",
                        "capacitance_pf",
                        "voltage",
                    ]:
                        value = 0.0
                    elif col == "actuated_channels":
                        value = []
                    else:
                        value = ""
                columnar_data[col].append(value)

        result = {
            "start_timestamp": self._metadata_entries.get("Start Time"),
            "columns": self._columns,
            "data": [columnar_data[col] for col in self._columns],
        }

        return result

    def save_data_file(self) -> Path | None:
        """save accumulated data to JSON file."""
        if not self._data_entries or not self._experiment_directory:
            logger.info("No data to save or no experiment directory")
            return None

        try:
            data_file_path = Path(
                self._experiment_directory / "data" / f"data_{self._metadata_entries.get("Start Time", get_current_utc_datetime())}.json"
            )

            data_file_path.parent.mkdir(parents=True, exist_ok=True)

            columnar_data = self._convert_to_columnar_format()

            with open(data_file_path, "w") as f:
                json.dump(columnar_data, f, separators=(",", ":"))

            logger.info(
                f"Saved {len(self._data_entries)} data entries to: {data_file_path}"
            )

            self._data_files.append(data_file_path)

            return data_file_path

        except Exception as e:
            logger.error(f"Error saving data file: {e}")
            return None

    def get_data_entry_count(self) -> int:
        """get number of logged data entries."""
        return len(self._data_entries)

    @staticmethod
    def load_data_as_dataframe(file_path: str):
        """
        Load the optimized JSON format and convert to pandas DataFrame.

        Args:
            file_path: Path to the JSON data file

        Returns:
            pandas.DataFrame: Data with proper column headers
        """
        try:
            with open(file_path, "r") as f:
                data = json.load(f)

            # extract values
            start_timestamp = data.get("start_timestamp")
            columns = data.get("columns", [])
            data_values = data.get("data", [])

            if not columns or not data_values:
                logger.warning("Empty or invalid data format")
                return pd.DataFrame()

            # create dataframe
            df_data = {}
            for i, col in enumerate(columns):
                if i < len(data_values):
                    df_data[col] = data_values[i]
                else:
                    df_data[col] = []

            df = pd.DataFrame(df_data)

            if start_timestamp:
                df["start_timestamp"] = start_timestamp

            logger.info(
                f"Loaded DataFrame with {len(df)} rows and {len(df.columns)} columns"
            )

            return df

        except ImportError:
            logger.error("pandas is required for loading data as DataFrame")
            return None
        except Exception as e:
            logger.error(f"Error loading data as DataFrame: {e}")
            return None

    def save_dataframe_as_csv(self, file_path: str | Path, output_path: str | Path = None):
        """
        Load JSON data and save as CSV file.

        Args:
            file_path: Path to the JSON data file
            output_path: Path for output CSV (optional, defaults to same directory)
        """
        try:
            df = self.load_data_as_dataframe(file_path)

            if df is None or df.empty:
                logger.warning("No data to save as CSV")
                return None

            if output_path is None:
                json_path = Path(file_path)
                output_path = json_path.parent / (json_path.stem + ".csv")

            df.to_csv(output_path, index=False)
            logger.critical(f"Saved CSV file: {output_path}")
            self._data_files.append(output_path)

            return str(output_path)

        except Exception as e:
            logger.error(f"Error saving CSV file: {e}")
            return None

    def _summarize_overall_data_to_html_table(self, file_path: str):
        df = self.load_data_as_dataframe(file_path)

        # 1. Isolate float columns and filter out all-zero columns
        float_cols = df.select_dtypes(include=["float"]).columns.tolist()
        active_floats = [col for col in float_cols if (df[col] != 0).any()]

        if not active_floats:
            return "<p>No active numeric data to summarize.</p>"

        # 2. Calculate global statistics for these columns
        # We transpose (.T) so columns become rows
        # We transpose (.T) so columns become rows"
        summary_df = df[active_floats].agg(["mean", "std", "min", "max"]).T

        summary_df.index.name = "Reading"

        # 4. Clean the Column Headers
        summary_df.columns = ["Average", "Std Dev", "Min", "Max"]

        # 5. Convert to HTML
        html_table = summary_df.to_html(
            classes="table table-striped table-hover",
            justify="center",
            na_rep="0.00",
            float_format=lambda x: f"{x:.2f}",
        )

        return html_table

    def get_files_summary(self, media_list, header):
        summary_str = ""

        if len(media_list) == 0:
            return summary_str

        summary_str += f"<h3>{header}</h3>"

        for i, el in enumerate(media_list):
            path_obj = Path(el)
            # file_url is for the 'under the hood' link
            file_url = path_obj.as_uri()
            # display_name is just the file (e.g., "video_01.mp4")
            display_name = path_obj.name

            media_file = ""

            if "Image" in header:
                media_file += f'<img src="{file_url}" width="360" height="240">'

            if "Video" in header:
                media_file += f"""
                                 <video width="360" height="240" controls>
                                  <source src={file_url} type="video/mp4">
                                Your browser does not support the video tag.
                                </video> """

            if "Note" in header:
                media_file += (
                    f'<iframe src={file_url} width="360" height="240"></iframe>'
                )

            clickable_path = f'<a href="{file_url}">{display_name}</a>' + media_file
            summary_str += f"<b>{i+1}.</b> {clickable_path}<br><br>"

        return summary_str

    def generate_report(self):
        # media files
        video_str = self.get_files_summary(self._video_captures, "Video Captures:")
        image_str = self.get_files_summary(self._image_captures, "Image Captures:")

        notes_str = ""
        # consume notes history for reporting if possible
        if hasattr(self.parent, "note_manager"):
            note_manager = getattr(self.parent, "note_manager")
            if isinstance(note_manager, StickyWindowManager):
                notes_str = self.get_files_summary(
                    note_manager.saved_notes_paths, "Notes Saved:"
                )
                note_manager.clear_saved_notes_history()

        # summarize data if we have any
        if self._data_files:
            # Get the file list string
            data_str = self.get_files_summary(self._data_files, "Data Files:")

            # Generate the HTML table for the first data file
            # Ensure this function returns the HTML table string
            data_summary_table = self._summarize_overall_data_to_html_table(self._data_files[0])

            # Wrap it in a header for the report
            data_section = f"""
                <h4>Data Summary:</h4>
                <div class="table-container">
                    {data_summary_table}
                </div>
            """
        else:
            data_str = ""
            data_section = ""


        # make meta data
        metadata_str = ""
        for key, val in self._metadata_entries.items():
            metadata_str += f"<b>{key}:</b> {val}<br><br>"

        report = f"""
            <h1>Run Summary</h1>
            <h2>Meta Data:</h2>
            {metadata_str}
            {data_section}
            {video_str}
            {image_str}
            {data_str}
            {notes_str}
        """

        return report

    def generate_and_save_report(self):
        report = self.generate_report()

        report_path = (
            Path(self._experiment_directory)
            / "reports"/ f"report_{get_current_utc_datetime()}.html"
        )

        report_path.parent.mkdir(parents=True, exist_ok=True)

        with report_path.open("w") as f:
            f.write(report)
            logger.critical(f"Run summary report saved to: {report_path}")
            self.last_saved_summary_path = report_path

        return report
