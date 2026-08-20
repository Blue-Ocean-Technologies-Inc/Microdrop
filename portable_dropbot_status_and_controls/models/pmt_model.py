from traits.api import Bool, Button, Range, Str

from portable_dropbot_controller.consts import (
    DEFAULT_PMT_GAIN, PMT_GAIN_BOUNDS,
)
from template_status_and_controls.base_model import BaseStatusModel

from ..consts import PORTABLE_DROPBOT_IMAGE


class PortableDropbotPmtModel(BaseStatusModel):
    """Qt-free state for the PMT pane: power, gain, and the vendor's
    acquire macro. Mutated only on the GUI thread."""

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    #: Mirrors the actual PMT power state the backend reports; a click
    #: that contradicts it is the user's request.
    pmt_power = Bool(False)
    pmt_gain = Range(*PMT_GAIN_BOUNDS, DEFAULT_PMT_GAIN,
                     mode="spinner",
                     desc="PMT gain (MCP41010 wiper position)")
    set_gain_button = Button("Set Gain")
    acquire_button = Button("Acquire")
    #: An acquire macro is running on the board (~10 s full buffer).
    acquiring = Bool(False)
    pmt_status_display = Str("-", desc="Last acquire outcome")
