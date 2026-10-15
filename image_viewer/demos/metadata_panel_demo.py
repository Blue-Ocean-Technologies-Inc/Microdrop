# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Show the image viewer's Metadata panel alone, for iterating on its
formatting without launching the app.

The sidebar's real ``metadata_group`` runs against a stand-in model; its
pop-out button opens the real ``metadata_window_view``. With a PNG path
the panel shows that file's facts and text chunks, otherwise a sample
capture's.

    pixi run python -m image_viewer.demos.metadata_panel_demo [image.png]
"""

# Standard library imports.
import json
import sys

# Enthought library imports.
from traits.api import Bool, Button, HasTraits, Str, observe
from traitsui.api import View

# Local imports.
from ..metadata import format_metadata_html, read_file_info, read_png_text
from ..view import metadata_group, metadata_window_view

#: A capture file's facts, shaped like ``read_file_info`` output.
SAMPLE_FILE_INFO = {
    "Dimensions": "1936 × 1096 px",
    "Pixel Format": "16-bit grayscale",
    "File Size": "4.1 MB",
    "Modified": "2026-10-15 14:03:27",
}

#: A fluorescence capture's chunk, shaped like the plugin's
#: ``capture_metadata`` output.
SAMPLE_TEXTS = {
    "CaptureDetails": json.dumps(
        {
            "version": "1.0.0",
            "timestamp_utc": "2026-10-15T14:03:27.512Z",
            "label": "GFP",
            "image_tag": "raw",
            "step_description": "Mix and image droplet 3",
            "step_dotted_id": "1.2",
            "wavelength": "470 nm",
            "led_index": 2,
            "intensity": "35 %",
            "frequency": "40000 Hz",
            "exposure": "120 ms",
            "requested_exposure": "120 ms",
            "auto_exposure": False,
            "camera_lead_time": "250 ms",
            "gain": 150,
            "requested_gain": 150,
            "auto_gain": False,
            "binning": 1,
            "image_type": "RAW16",
            "sensor_temperature": "24.6 °C",
            "field_descriptions": {
                "timestamp_utc": "When the image was captured, in UTC.",
                "label": (
                    "Name of the capture: image tag, wavelength and chain "
                    "position; also the start of its file name."
                ),
                "image_tag": (
                    "Optional tag the user gave the capture, leading its label."
                ),
                "step_description": (
                    "Protocol step that took the capture (null when run from "
                    "the controls pane)."
                ),
                "step_dotted_id": (
                    "Position of that step in the protocol tree, e.g. 1.2."
                ),
                "wavelength": (
                    "LED colour that lit the sample, or Multi-Channel for a mix."
                ),
                "led_index": (
                    "Controller channel number (from 0) of the LED that was lit."
                ),
                "led_intensities": (
                    "Brightness (PWM duty cycle) of each LED channel in the "
                    "mix, by channel number."
                ),
                "intensity": (
                    "LED brightness as a PWM duty cycle; for a mix, the master "
                    "level that each channel's share scales."
                ),
                "frequency": "PWM switching frequency of the lit LED(s).",
                "exposure": "Exposure time the image was actually taken with.",
                "requested_exposure": (
                    "Exposure time set for the capture; only the starting "
                    "point when auto exposure is on."
                ),
                "auto_exposure": (
                    "Whether exposure was adjusted automatically toward a "
                    "target brightness."
                ),
                "camera_lead_time": (
                    "Extra wait after the LED settled before the image was "
                    "taken, so exposure and gain could settle."
                ),
                "gain": "Camera gain the image was actually taken with.",
                "requested_gain": (
                    "Camera gain set for the capture; only the starting point "
                    "when auto gain is on."
                ),
                "auto_gain": (
                    "Whether gain was adjusted automatically toward a target "
                    "brightness."
                ),
                "binning": (
                    "Sensor pixels combined into one image pixel along each "
                    "side (1 = full resolution)."
                ),
                "image_type": (
                    "Camera readout format of the frame, e.g. raw16 for 16-bit raw."
                ),
                "sensor_temperature": (
                    "Camera sensor temperature last read when the image was "
                    "saved (null before the first reading)."
                ),
            },
        }
    )
}


class MetadataPanelDemo(HasTraits):
    """The slice of the image viewer model the Metadata panel reads."""

    show_metadata = Bool(True)
    metadata_text = Str()
    metadata_popout_button = Button()

    @observe("metadata_popout_button")
    def _pop_out(self, event):
        self.edit_traits(view=metadata_window_view)


def main():
    if len(sys.argv) > 1:
        file_info, texts = read_file_info(sys.argv[1]), read_png_text(sys.argv[1])
    else:
        file_info, texts = SAMPLE_FILE_INFO, SAMPLE_TEXTS

    demo = MetadataPanelDemo(metadata_text=format_metadata_html(file_info, texts))

    demo.configure_traits(
        view=View(
            metadata_group,
            title="Metadata panel",
            resizable=True,
            scrollable=True,
            width=280,
            height=560,
        )
    )


if __name__ == "__main__":
    main()
