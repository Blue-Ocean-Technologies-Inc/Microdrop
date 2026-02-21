import json
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
from PySide6.QtCore import QTimer

from device_viewer.models.media_capture_model import MediaCaptureMessageModel, MediaType
from microdrop_utils.datetime_helpers import (
    TimestampedMessage,
    get_current_utc_datetime,
    get_elapsed_time_from_utc_datetime,
)
import plotly.express as px

from microdrop_utils.plotly_helpers import create_plotly_svg_dropbot_device_heatmap
from microdrop_utils.sticky_notes import StickyWindowManager

from logger.logger_service import get_logger

logger = get_logger(__name__)

from microdrop_application.helpers import get_microdrop_redis_globals_manager

app_globals = get_microdrop_redis_globals_manager()

from functools import wraps


def require_active_logging(func):
    """Decorator to ensure logging is active before executing a method."""

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not getattr(self, "_is_logging_active", False):
            logger.debug(
                f"Attempted to call '{func.__name__}', but logger is not active."
            )
            return None  # Early exit
        return func(self, *args, **kwargs)

    return wrapper


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
        self._active_analysis_df = None

        self._columns = []

    def start_logging(
        self,
        experiment_directory: Path | str,
        device_svg_path: Path | str,
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
        app_globals["media_captures"] = []

        # set flags
        self._is_logging_active = True
        self._preview_mode = preview_mode

        # set metadata
        self._experiment_directory = experiment_directory
        self._svg_file = device_svg_path
        self._total_nsteps = n_steps
        self._start_timestamp = get_current_utc_datetime()

        self.log_metadata(
            {
                "Experiment Directory": f'<a href="file:///{self._experiment_directory}">{Path(self._experiment_directory).name}</a>',
                "Device Svg": f'<a href="file:///{self._svg_file}">{Path(self._svg_file).name}</a>',
                "Steps Completed": f"0 / {self._total_nsteps}",
            }
        )

        logger.info(
            f"Started protocol data logging to: {experiment_directory} at {self._start_timestamp}"
        )

    @require_active_logging
    def stop_logging(self, completed_steps=None, settling_time_ms=2000):

        # log metadata before stopping the logging

        _completed_nsteps = completed_steps if completed_steps else self._total_nsteps

        _stop_timestamp = get_current_utc_datetime()
        _elapsed_time = get_elapsed_time_from_utc_datetime(
            self._start_timestamp, _stop_timestamp
        )

        self.log_metadata(
            {
                "Start Time": self._start_timestamp,
                "Stop Time": _stop_timestamp,
                "Elapsed Time": _elapsed_time,
                "Steps Completed": f"{_completed_nsteps} / {self._total_nsteps}",
            }
        )

        # receive logs for another few seconds for background processes to settle
        def _block_logging():
            self._is_logging_active = False

        QTimer.singleShot(settling_time_ms, _block_logging)

        logger.info(
            f"Stopped protocol data logging at {self._start_timestamp} after {_elapsed_time}.\n"
            f"Further logs will be allowed for {settling_time_ms} for background tasks to settle and input logs."
        )

    def set_protocol_context(self, context: Dict):
        self._current_protocol_context = context

    def update_capacitance_per_unit_area(self, c_unit_area: float):
        self._latest_capacitance_per_unit_area = c_unit_area
        logger.debug(f"Updated capacitance per unit area: {c_unit_area}")

    def log_media_capture(self, message: MediaCaptureMessageModel, force=False):
        if not self._is_logging_active and not force:
            logger.warning("Logger not active")
            return

        if message.type == MediaType.VIDEO:
            self._video_captures.append(message.path)
        elif message.type == MediaType.IMAGE:
            self._image_captures.append(message.path)
        elif message.type == MediaType.OTHER:
            self._other_media_captures.append(message.path)

    @require_active_logging
    def log_data(self, data_point: dict):
        # Automatically add a timestamp if it's missing
        if "utc_time" not in data_point:
            data_point["utc_time"] = get_current_utc_datetime()

        self._data_entries.append(data_point)

        # Automatically keep track of columns seen so far
        for key in data_point.keys():
            if key not in self._columns:
                self._columns.append(key)

    @require_active_logging
    def log_metadata(self, data_point: dict):
        self._metadata_entries.update(data_point)

    @require_active_logging
    def log_capacitance_data(self, capacitance_message: TimestampedMessage):
        try:
            # parse capacitance message
            capacitance_data = json.loads(capacitance_message)
            capacitance_str = capacitance_data.get("capacitance", "-")
            voltage_str = capacitance_data.get("voltage", "-")
            instrument_timestamp_us = capacitance_data.get("instrument_time_us", 0)
            reception_timestamp = capacitance_data.get("reception_time", 0)

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
                "step_idx": step_idx,
                "utc_time": int(
                    reception_timestamp
                ),  # we care only about precision to the second.
                "instrument_time_us": instrument_timestamp_us,
                "step_id": step_id,
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
        """Convert list of entry dictionaries to columnar."""
        if not self._data_entries:
            return {
                "columns": self._columns,
                "data": [[] for _ in self._columns],
            }

        columnar_data = {col: [] for col in self._columns}

        for entry in self._data_entries:
            for col in self._columns:
                value = entry.get(col)
                columnar_data[col].append(value)

        result = {
            "columns": self._columns,
            "data": [columnar_data[col] for col in self._columns],
        }

        return result

    @staticmethod
    def load_data_as_dataframe(json_data=None):
        """
        Load the optimized JSON format and convert to pandas DataFrame.

        Args:
            file_path: Optional Path to the JSON data file
            json_data: Optional JSON data. Used directly even if filepath provided

        Returns:
            pandas.DataFrame: Data with proper column headers
        """
        try:

            data = json.loads(json_data)

            # extract values
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

    def save_data_file(self) -> Path | None:
        """save accumulated data to JSON file."""
        if not self._data_entries or not self._experiment_directory:
            logger.info("No data to save or no experiment directory")
            return None

        try:
            data_file_path = Path(
                self._experiment_directory
                / "data"
                / f"data_{self._metadata_entries.get("Start Time", get_current_utc_datetime())}.json"
            )

            data_file_path.parent.mkdir(parents=True, exist_ok=True)

            columnar_data = self._convert_to_columnar_format()
            json_str = json.dumps(columnar_data, separators=(",", ":"))

            df = self.load_data_as_dataframe(json_data=json_str)

            ### Compute corrected instrument time ######
            # 1. Define the 32-bit limit
            # 2**32 = 4,294,967,296
            UINT32_MAX = 2**32

            # 2. Calculate difference between steps
            diffs = df["instrument_time_us"].diff()

            # 3. Detect Rollover
            # If the difference is a huge negative number (e.g., < -2 billion), a rollover occurred.
            rollovers = diffs < -(UINT32_MAX // 2)

            # 4. Calculate the offset
            # Each time a rollover happens, we add 2^32 to all subsequent values
            rollover_offsets = rollovers.cumsum() * UINT32_MAX

            # 5. Apply correction
            df["corr_instrument_time_us"] = df["instrument_time_us"] + rollover_offsets

            df.to_json(data_file_path)

            logger.info(
                f"Saved {len(self._data_entries)} data entries to: {data_file_path}"
            )

            self._active_analysis_df = df

            return data_file_path

        except Exception as e:
            logger.error(f"Error saving data file: {e}")
            return None

    def get_data_entry_count(self) -> int:
        """get number of logged data entries."""
        return len(self._data_entries)

    def save_dataframe_as_csv(
        self, file_path: str | Path = None, output_path: str | Path = None
    ):
        """
        Load JSON data and save as CSV file.

        Args:
            file_path: Path to the JSON data file
            output_path: Path for output CSV (optional, defaults to same directory)
        """
        try:
            df = pd.read_json(file_path) if file_path else self._active_analysis_df

            if df is None or df.empty:
                logger.warning("No data to save as CSV")
                return None

            if output_path is None:
                json_path = Path(file_path)
                output_path = json_path.parent / (json_path.stem + ".csv")

            df.to_csv(output_path, index=False)
            logger.critical(f"Saved CSV file: {output_path}")
            self._data_files.append(output_path)

            return output_path

        except Exception as e:
            logger.error(f"Error saving CSV file: {e}")
            return None

    def _summarize_overall_data_to_html_table(self):
        df = self._active_analysis_df

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

    def _get_channel_duration(self) -> dict:
        df = self._active_analysis_df

        # find number of data points recorded for each channel
        num_data_points_per_channel = df.explode("actuated_channels")[
            "actuated_channels"
        ].value_counts()

        # find average time
        df["step_delta"] = df["corr_instrument_time_us"].diff()

        # insturment time is in us, convert to seconds * 1e-6
        average_capacitance_update_interval_s = (
            df.sort_values("corr_instrument_time_us")["corr_instrument_time_us"]
            .diff()
            .fillna(0)
            .mean()
            * 1e-6
        )

        # multiply n hits by update time to get estimated channel actuation duration.
        channel_duration_series = (
            num_data_points_per_channel * average_capacitance_update_interval_s
        )

        return channel_duration_series.to_dict()

    def _create_html_plots_for_all_float_columns(self):
        df = self._active_analysis_df

        # 1. Filter active float columns
        float_cols = df.select_dtypes(include=["float"]).columns.tolist()
        active_floats = [col for col in float_cols if (df[col] != 0).any()]

        if not active_floats:
            return "<p>No active numeric data to summarize.</p>"

        plots_html = '<div style="display: flex; flex-direction: column; gap: 80px; width: 100%;">'

        for col in active_floats:
            # 2. Group by both Index and ID to keep the ID available for the label
            # We sort by index to ensure chronological order top-to-bottom
            stats = (
                df.groupby(["step_idx", "step_id"])[col]
                .agg(["mean", "std"])
                .reset_index()
            )
            stats = stats.sort_values("step_idx", ascending=False)

            # 3. Create Horizontal Bar Chart
            fig = px.bar(
                stats,
                x="mean",
                y="step_id",
                error_x="std",  # Horizontal error bars
                orientation="h",
                title=col,
                labels={"mean": f"Average {col}", "step_id": "step_id"},
                template="plotly_white",
                color_discrete_sequence=["#17a2b8"],  # Nice teal color
            )

            # 4. Refine the axis to show every Step ID clearly
            fig.update_layout(
                yaxis=dict(type="category", title="Protocol Steps"),
                xaxis=dict(title=f"Mean {col}"),
                margin=dict(l=20, r=20, t=50, b=20),
                # Height grows with the number of steps to prevent overlap
                height=250 + (len(stats) * 35),
            )

            fig_div = fig.to_html(full_html=False, include_plotlyjs="cdn")

            plots_html += f"""
                <div style="width: 100%; padding-bottom: 40px; border-bottom: 2px solid #f0f0f0;">
                    {fig_div}
                </div>
            """

        plots_html += "</div>"
        return plots_html

    ############### Data processing to html methods ###########################

    def _get_files_summary(self, media_list, media_type):
        summary_str = ""

        if len(media_list) == 0:
            return summary_str

        for i, el in enumerate(media_list):
            path_obj = Path(el)
            # file_url is for the 'under the hood' link
            file_url = path_obj.as_uri()
            # display_name is just the file (e.g., "video_01.mp4")
            display_name = path_obj.name

            media_file = ""

            if "Image" in media_type:
                media_file += f'<br><br><img src="{file_url}" width="360" height="240">'

            if "Video" in media_type:
                # We create a placeholder DIV.
                # The 'onclick' JavaScript swaps this DIV for the actual VIDEO tag when clicked.
                # We use single quotes escaped with backslashes (\') inside the HTML string to avoid conflicts.
                media_file += f"""
                        <br><br>
                        <div onclick="this.outerHTML='<video width=\\'360\\' height=\\'240\\' controls autoplay><source src=\\'{file_url}\\' type=\\'video/mp4\\'>Your browser does not support the video tag.</video>'" 
                             style="cursor: pointer; 
                                    width: 360px; 
                                    height: 240px; 
                                    background-color: #000; 
                                    display: flex; 
                                    align-items: center; 
                                    justify-content: center; 
                                    position: relative;">

                            <div style="font-size: 50px; color: white;">&#9658;</div>
                        </div> 
                    """

            if "Note" in media_type:
                media_file += (
                    f'<br><br><iframe src={file_url} width="360" height="240"></iframe>'
                )

            clickable_path = f'<a href="{file_url}">{display_name}</a>' + media_file
            summary_str += f"<b>{i+1}.</b> {clickable_path}<br><br>"

        return summary_str

    def _get_data_str(self):
        try:
            data_str = self._get_files_summary(self._data_files, "Data Files:")
        except Exception as e:
            logger.error(e, exc_info=True)
            data_str = e

        return data_str

    def _get_overall_data_summary_table(self):
        ## create overall data summary table
        try:
            data_section = f"""
                                    <div class="table-container">
                                        {self._summarize_overall_data_to_html_table()}
                                    </div>
                                """

        except Exception as e:
            logger.error(e, exc_info=True)
            data_section = e

        return data_section

    def _get_data_visuals(self):
        try:
            device_svg_heatmap_plotly_fig = create_plotly_svg_dropbot_device_heatmap(
                svg_file=self._svg_file,
                channel_quantity_dict=self._get_channel_duration(),
            )

            data_visuals_section = f"""
                                    <div class="table-container">
                                        {device_svg_heatmap_plotly_fig.to_html(full_html=False, include_plotlyjs="cdn")} <br>
                                        {self._create_html_plots_for_all_float_columns()}
                                    </div>
                                """

        except Exception as e:
            logger.error(e, exc_info=True)
            data_visuals_section = e

        return data_visuals_section

    def _generate_report_html(self):

        notes_str = ""
        # consume notes history for reporting if possible
        if hasattr(self.parent, "note_manager"):
            note_manager = getattr(self.parent, "note_manager")
            if isinstance(note_manager, StickyWindowManager):
                notes_str = self._get_files_summary(
                    note_manager.saved_notes_paths, "Notes Saved:"
                )
                note_manager.clear_saved_notes_history()

        # make meta data
        metadata_str = ""
        for key, val in self._metadata_entries.items():
            metadata_str += f"<b>{key}:</b> {val}<br><br>"

        # make data analysis sections using data files, if they exist.
        data_str = data_section = data_visuals_section = ""
        if self._data_files:
            # Get the file list string
            data_str, data_section, data_visuals_section = (
                self._get_data_str(),
                self._get_overall_data_summary_table(),
                self._get_data_visuals(),
            )

        report = f"""
            <h1>Run Summary</h1>
            
            <h2>Meta Data:</h2>
            {metadata_str}
            
            <h2>Data Files:</h2>
            {data_str}
            
            <h2>Data Summary:</h2>
            {data_section}
            
            <h2>Data Trends:</h2>
            {data_visuals_section}
            
            <h2>Media Captures:</h2>
            
            <h3>Video Captures:</h3>
            {self._get_files_summary(self._video_captures, "Video")}
            
            <h3>Image Captures:</h3>
            {self._get_files_summary(self._image_captures, "Image")}
            
            <h2>Notes:</h2>
            {notes_str}
        """

        return report

    #############################################################################

    def generate_and_save_report(self, report_path=None):
        # save data files
        self.generate_data_files()

        ### Consume media files ####
        media_captures = app_globals.get("media_captures")

        for media_capture in media_captures:
            logger.info(f"Media Captured: {media_capture}")
            msg = MediaCaptureMessageModel.model_validate_json(media_capture)
            self.log_media_capture(msg, force=True)

        #############################

        report = self._generate_report_html()

        if not report_path:

            report_path = (
                Path(self._experiment_directory)
                / "reports"
                / f"report_{get_current_utc_datetime()}.html"
            )

        report_path.parent.mkdir(parents=True, exist_ok=True)

        with report_path.open("w") as f:
            f.write(report)
            logger.critical(f"Run summary report saved to: {report_path}")
            self.last_saved_summary_path = report_path

        # cleanup:
        del self._active_analysis_df

        return report

    def generate_data_files(self):
        self._data_files = []

        data_file_path = self.save_data_file()

        if data_file_path:
            self._data_files.append(data_file_path)

            csv_file_path = self.save_dataframe_as_csv(
                output_path=data_file_path.with_suffix(".csv")
            )

            if csv_file_path:
                self._data_files.append(csv_file_path)


if __name__ == "__main__":

    from pathlib import Path

    file = Path(
        "C:\\Users\\Info\\Documents\\Sci-Bots\\Microdrop\\Experiments\\2026_02_03-19_56_22\\data\\data_2026_02_03-19_57_54.json"
    )

    df = ProtocolDataLogger.load_data_as_dataframe(str(file))

    # 1. Define the 32-bit limit
    # 2**32 = 4,294,967,296
    UINT32_MAX = 2**32

    # 2. Calculate difference between steps
    diffs = df["instrument_time_us"].diff()

    # 3. Detect Rollover
    # If the difference is a huge negative number (e.g., < -2 billion), a rollover occurred.
    rollovers = diffs < -(UINT32_MAX // 2)

    # 4. Calculate the offset
    # Each time a rollover happens, we add 2^32 to all subsequent values
    rollover_offsets = rollovers.cumsum() * UINT32_MAX

    # 5. Apply correction
    df["corr_instrument_time_us"] = df["instrument_time_us"] + rollover_offsets

    df["delta"] = df["corr_instrument_time_us"] - df["instrument_time_us"]

    print(df[["instrument_time_us", "corr_instrument_time_us", "delta"]])
