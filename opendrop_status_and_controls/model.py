from traits.api import Str

from opendrop_status.consts import OPENDROP_IMAGE
from template_status_and_controls.base_model import BaseStatusModel

from logger.logger_service import get_logger

logger = get_logger(__name__)


class OpendropStatusAndControlsModel(BaseStatusModel):
    """Model for OpenDrop status display and controls.

    Extends BaseStatusModel with OpenDrop-specific sensor readings.
    Connection/mode/icon traits and their observers are inherited.
    """

    # ---- Class-level constants ----------------------------------------
    DEFAULT_ICON_PATH = OPENDROP_IMAGE
    # Colors use BaseStatusModel defaults (SUCCESS/WARNING/GREY), which match.

    # ---- Device-specific traits ---------------------------------------
    board_id = Str("-", desc="OpenDrop board identifier")
    temperature_1 = Str("-", desc="Temperature channel 1 (°C)")
    temperature_2 = Str("-", desc="Temperature channel 2 (°C)")
    temperature_3 = Str("-", desc="Temperature channel 3 (°C)")
    feedback_active_channels = Str("-", desc="Number of active feedback channels")
