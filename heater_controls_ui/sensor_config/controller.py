"""Handler for the Configure Sensors & Heaters dialog.

Button actions publish board requests (scan / refresh / save-and-push) and save
the edited config to a file. Board responses flow back asynchronously through
the heater message handler into the shared SensorConfigModel, so the dialog
never touches the serial port itself.
"""
import json

from traitsui.api import Controller
from pydantic import ValidationError
from pyface.api import YES

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.traitsui_qt_helpers import stretch_group_layouts_horizontally
from microdrop_application.dialogs.pyface_wrapper import (
    error, information, confirm, file_dialog,
)
from heater_controller.consts import SCAN_SENSORS, DUMP_CONFIG, SAVE_CONFIG_TO_BOARD
from heater_controller.datamodels import HeaterConfigEdit, SensorNaming

from .parsing import build_board_config, split_sensor_names, thermistor_names

from logger.logger_service import get_logger
logger = get_logger(__name__)


class SensorConfigController(Controller):
    """TraitsUI handler: maps the dialog's buttons to board requests + file save."""

    def init(self, info):
        """Stretch the top labels/tables to the full dialog width (TraitsUI
        otherwise left-hugs them, which starves the word-wrapped help text and
        makes it wrap to a sliver)."""
        stretch_group_layouts_horizontally(info.ui.control)
        return super().init(info)

    # ------------------------------------------------------------------ #
    # Board requests                                                       #
    # ------------------------------------------------------------------ #
    def scan_sensors(self, info=None):
        logger.info("Configurator: requesting a 1-Wire sensor scan")
        publish_message(message="", topic=SCAN_SENSORS)

    def refresh_from_board(self, info=None):
        logger.info("Configurator: requesting a config refresh from the board")
        publish_message(message="", topic=DUMP_CONFIG)

    # ------------------------------------------------------------------ #
    # Save                                                                 #
    # ------------------------------------------------------------------ #
    def save_to_file(self, info=None):
        """Validate the edited rows and write the new config to a chosen file."""
        new_config = self._validated_config(info.object)
        if new_config is None:
            return
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

    def save_and_push(self, info=None):
        """Validate the edited rows, confirm, then ask the backend to write the
        config onto the board and reboot it."""
        new_config = self._validated_config(info.object)
        if new_config is None:
            return
        if confirm(message="Write this configuration to the board and reboot it?",
                   informative="The heater will disconnect briefly while it reboots.",
                   title="Save && push to board") != YES:
            return
        publish_message(message=json.dumps(new_config), topic=SAVE_CONFIG_TO_BOARD)
        information(
            message="Pushing the configuration to the board.",
            informative="It will reboot and reconnect shortly.", title="Pushing config")

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _validated_config(model):
        """Build the new config dict from the edited rows, or None (after showing
        an error dialog) when the edit fails validation."""
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
            return None
        return build_board_config(model.config, named, assignments)
