"""Handler for the Configure Sensors & Heaters dialog.

Button actions publish board requests (scan / refresh) and save the edited
config to a file. Board responses flow back asynchronously through the heater
message handler into the shared SensorConfigModel, so the dialog never touches
the serial port itself.
"""
import json

from traitsui.api import Controller
from pydantic import ValidationError

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_application.dialogs.pyface_wrapper import error, information, file_dialog
from heater_controller.consts import SCAN_SENSORS, DUMP_CONFIG
from heater_controller.datamodels import HeaterConfigEdit, SensorNaming

from .parsing import build_board_config, split_sensor_names, thermistor_names

from logger.logger_service import get_logger
logger = get_logger(__name__)


class SensorConfigController(Controller):
    """TraitsUI handler: maps the dialog's buttons to board requests + file save."""

    def scan_sensors(self, info=None):
        logger.info("Configurator: requesting a 1-Wire sensor scan")
        publish_message(message="", topic=SCAN_SENSORS)

    def refresh_from_board(self, info=None):
        logger.info("Configurator: requesting a config refresh from the board")
        publish_message(message="", topic=DUMP_CONFIG)

    def save_to_file(self, info=None):
        """Validate the edited rows, build the new config, and write it to a
        user-chosen JSON file. Validation errors and I/O errors are surfaced as
        dialogs; nothing is written unless the edit is valid."""
        model = info.object

        # Only non-empty names persist (a cleared name removes that sensor).
        named = [(r.rom, r.name.strip()) for r in model.sensors if r.name.strip()]
        assignments = {r.heater: split_sensor_names(r.sensors)
                       for r in model.heater_assignments}

        try:
            HeaterConfigEdit(
                sensors=[SensorNaming(rom=rom, name=name) for rom, name in named],
                assignments=assignments,
                thermistor_names=thermistor_names(model.config),
            )
        except ValidationError as exc:
            details = "\n".join(
                f"• {err['msg'].replace('Value error, ', '')}" for err in exc.errors())
            error(message="The configuration can't be saved:", informative=details,
                  title="Invalid configuration")
            return

        new_config = build_board_config(model.config, named, assignments)

        path = file_dialog(action="save", default_path="config.json",
                           wildcard="JSON files (*.json)|*.json|All files (*.*)|*.*")
        if not path:
            return
        try:
            with open(path, "w") as fh:
                json.dump(new_config, fh, indent=2)
                fh.write("\n")
        except OSError as exc:
            error(message="Could not write the config file:", informative=str(exc),
                  title="Save failed")
            return

        logger.info(f"Configurator: wrote config to {path}")
        information(message=f"Saved configuration to:\n{path}", title="Saved")
