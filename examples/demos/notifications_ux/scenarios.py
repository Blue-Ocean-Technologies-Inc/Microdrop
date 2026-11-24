# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""What the prototype posts, and what its buttons pretend to do.

Scenarios post through the real NOTIFICATION_POST topic (on the demo's
private Redis), as plugins would; the start-up history goes straight into
the centre, as if posted before the window was up. Buttons never act: the
responder logs and posts what would have happened.
"""

# Standard library imports.
import threading
import time
import traceback

# Enthought library imports.
from pyface.api import GUI
from traits.api import HasTraits, Instance

# Microdrop package imports.
from examples.demos.notifications_pane.sample_notifications import post_log_samples
from notifications.consts import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_SUCCESS,
    SEVERITY_WARNING,
    OpenPathAction,
    PublishAction,
)

# Local imports.
from .ux_consts import HelpAction, SnoozeAction, ux_notification_publisher
from .ux_models import UxNotificationCenter

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The demo's own logger for the flood, kept off the console.
flood_logger = get_logger("notifications_ux_demo.flood")
flood_logger.propagate = False

#: Records the flood emits from its thread, and distinct ones among them.
FLOOD_RECORDS = 5000
FLOOD_DISTINCT = 12

#: Notifications in a burst.
BURST_SIZE = 20

#: Demo topics the cards' buttons "publish".
CALIBRATE_TOPIC = "demo/calibrate"
UPDATE_PLUGINS_TOPIC = "demo/update_plugins"
RESTART_TOPIC = "demo/restart"
RETRY_CONNECTION_TOPIC = "demo/retry_connection"
CHIP_INSERTED_TOPIC = "demo/chip_inserted"
OPEN_REPORT_TOPIC = "demo/open_report"

#: Milliseconds a pretend job takes before it reports back.
JOB_MS = 2500

CALIBRATION_DETAIL = (
    "Recalibrate before quantitative runs: capacitance readings drift over time."
)

PLUGIN_UPDATES_DETAIL = (
    "heater-microdrop-plugin 1.4.0 → 1.5.0\n"
    "magnet-microdrop-plugin 0.9.2 → 0.10.0\n"
    "Updating takes about a minute; MicroDrop restarts afterwards."
)


def _publish(**fields):
    """Post a notification through the topic, as any plugin would."""
    ux_notification_publisher.publish(fields)


def _traceback_of(error_type, message):
    """A real traceback, raised and caught here."""

    def connect():
        raise error_type(message)

    try:
        connect()

    except error_type:
        return traceback.format_exc()


# ---------------------------------------------------------------------------
# Single notifications
# ---------------------------------------------------------------------------


def post_info():
    _publish(
        title="Device changed to 90-pin chip",
        detail="Loaded 90_pin_array.svg from the device library.",
        severity=SEVERITY_INFO,
        category="device",
        source="device_viewer",
    )


def post_success():
    _publish(
        title="Protocol saved",
        detail="Saved as sample_prep_v3.json in the experiment folder.",
        severity=SEVERITY_SUCCESS,
        category="protocol",
        source="pluggable_protocol_tree",
    )


def post_warning():
    _publish(
        title="Low liquid level on electrode 42",
        detail=(
            "The droplet's capacitance fell below 60 % of its starting value "
            "during step 5. The droplet may have split or evaporated; check "
            "the chip before running the next step."
        ),
        severity=SEVERITY_WARNING,
        category="hardware",
        source="dropbot_controller",
        secondary_action=HelpAction(
            tutorial="Droplet detection and volume"
        ).model_dump(),
    )


def post_error():
    _publish(
        title="Could not connect to the DropBot on COM5",
        detail=_traceback_of(ConnectionError, "COM5: the device did not answer in 3 s"),
        severity=SEVERITY_ERROR,
        category="hardware",
        source="dropbot_controller",
        action=PublishAction(label="Retry", topic=RETRY_CONNECTION_TOPIC).model_dump(),
        secondary_action=HelpAction(
            label="How do I connect?", tutorial="Connecting a DropBot"
        ).model_dump(),
    )


def post_action_required():
    _publish(
        title="Insert a chip to continue",
        detail=(
            "The protocol is paused at step 3: no chip is detected in the "
            "DropBot. Insert one, close the lid, then continue."
        ),
        severity=SEVERITY_WARNING,
        category="hardware",
        source="dropbot_status_and_controls",
        needs_attention=True,
        action=PublishAction(
            label="I've inserted it", topic=CHIP_INSERTED_TOPIC
        ).model_dump(),
        secondary_action=HelpAction(
            label="How do I insert a chip?", tutorial="Inserting a chip"
        ).model_dump(),
    )


def post_plugin_updates():
    _publish(
        title="Plugin updates available",
        detail=PLUGIN_UPDATES_DETAIL,
        severity=SEVERITY_INFO,
        category="plugins",
        source="plugin_management",
        needs_attention=True,
        action=PublishAction(
            label="Update plugins", topic=UPDATE_PLUGINS_TOPIC
        ).model_dump(),
        secondary_action=SnoozeAction().model_dump(),
    )


def post_protocol_finished(folder):
    _publish(
        title="Protocol finished",
        detail=(
            "8 steps in 2 min 41 s. The report and video are in the experiment folder."
        ),
        severity=SEVERITY_SUCCESS,
        category="protocol",
        source="pluggable_protocol_tree",
        action=OpenPathAction(label="Show folder", path=folder).model_dump(),
    )


def post_calibration_old():
    _publish(
        title="Calibration is 9 days old",
        detail=CALIBRATION_DETAIL,
        severity=SEVERITY_WARNING,
        category="calibration",
        source="dropbot_status_and_controls",
        needs_attention=True,
        action=PublishAction(label="Calibrate", topic=CALIBRATE_TOPIC).model_dump(),
        secondary_action=HelpAction(
            label="How do I calibrate?", tutorial="Calibrating the device"
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# Many at once
# ---------------------------------------------------------------------------

_BURST_TEXTS = [
    ("Step {n} finished", SEVERITY_SUCCESS, "pluggable_protocol_tree"),
    ("Electrode {n} disabled: short detected", SEVERITY_WARNING, "dropbot_controller"),
    ("Captured frame {n}", SEVERITY_INFO, "image_viewer"),
    ("ROI {n} intensity above threshold", SEVERITY_INFO, "image_viewer"),
]


def post_burst():
    """BURST_SIZE distinct notifications at once."""

    for number in range(1, BURST_SIZE + 1):
        text, severity, source = _BURST_TEXTS[number % len(_BURST_TEXTS)]
        _publish(
            title=text.format(n=number),
            severity=severity,
            source=source,
            category="burst",
        )


def flood_from_thread():
    """FLOOD_RECORDS warnings from a worker thread, through the log handler
    (which collapses repeats), and FLOOD_DISTINCT topic posts."""

    def flood():
        for number in range(FLOOD_RECORDS):
            flood_logger.warning(f"Stage {number % 3} drifted past its limit")

        for number in range(FLOOD_DISTINCT):
            _publish(
                title=f"Heater zone {number} overshoot",
                severity=SEVERITY_WARNING,
                source="heater_controller",
                category="hardware",
            )

    threading.Thread(target=flood, name="notifications demo flood", daemon=True).start()


# ---------------------------------------------------------------------------
# Start-up history
# ---------------------------------------------------------------------------


def post_history(center, folder):
    """What a session would hold by the time the window is up: real (scrubbed)
    log records, an earlier protocol run, and an old calibration."""
    now = time.time()

    post_log_samples(center, now)

    center.post(
        "Protocol finished",
        detail="24 steps in 6 min 12 s. The report is in the experiment folder.",
        severity=SEVERITY_SUCCESS,
        category="protocol",
        source="pluggable_protocol_tree",
        timestamp=now - 1500,
        action=OpenPathAction(label="Show folder", path=folder),
    )
    center.post(
        "Calibration is 9 days old",
        detail=CALIBRATION_DETAIL,
        severity=SEVERITY_WARNING,
        category="calibration",
        source="dropbot_status_and_controls",
        timestamp=now - 600,
        needs_attention=True,
        action=PublishAction(label="Calibrate", topic=CALIBRATE_TOPIC),
        secondary_action=HelpAction(
            label="How do I calibrate?", tutorial="Calibrating the device"
        ),
    )


# ---------------------------------------------------------------------------
# What the buttons pretend to do
# ---------------------------------------------------------------------------


class DemoResponder(HasTraits):
    """Stands in for what a card's buttons would do: logs it and posts the
    outcome a real handler would."""

    center = Instance(UxNotificationCenter)

    def publish(self, topic, message=""):
        """A PublishAction's topic, answered as its handler would."""
        logger.info(f"Demo: a card's button would publish {topic}")
        answer = _ANSWERS.get(topic)

        if answer is None:
            self._post(f"Would publish {topic}", SEVERITY_INFO)

            return

        first, then = answer
        self._post(*first)

        if then is not None:
            GUI.invoke_after(JOB_MS, self._post, *then)

    def open_path(self, path):
        """An OpenPathAction: no window opens in the demo."""
        logger.info(f"Demo: would open {path} in the file browser")
        self._post("Would open the folder in the file browser", SEVERITY_INFO, path)

    def open_tutorial(self, tutorial):
        """A HelpAction: names the tutorial it would open."""
        logger.info(f"Demo: would open the tutorial {tutorial!r}")
        self._post(
            f"Would open the tutorial: {tutorial}",
            SEVERITY_INFO,
            "Help > Tutorials would open on this page, scrolled to the steps.",
        )

    def _post(self, title, severity, detail="", action=None):
        self.center.post(
            title,
            detail=detail,
            severity=severity,
            source="notifications demo",
            action=action,
        )


#: Each demo topic's immediate answer and, after JOB_MS, its outcome:
#: (title, severity, detail[, action]).
_ANSWERS = {
    CALIBRATE_TOPIC: (
        (
            "Calibrating…",
            SEVERITY_INFO,
            "Keep the lid closed; this takes about a minute.",
        ),
        (
            "Calibration done",
            SEVERITY_SUCCESS,
            "Capacitance offsets updated for all 90 channels.",
        ),
    ),
    UPDATE_PLUGINS_TOPIC: (
        (
            "Updating 2 plugins…",
            SEVERITY_INFO,
            "heater-microdrop-plugin, magnet-microdrop-plugin",
        ),
        (
            "Plugins updated",
            SEVERITY_SUCCESS,
            "Restart MicroDrop to use the new versions.",
            PublishAction(label="Restart now", topic=RESTART_TOPIC),
        ),
    ),
    RETRY_CONNECTION_TOPIC: (
        (
            "Looking for a DropBot…",
            SEVERITY_INFO,
            "Trying COM5, then every other port.",
        ),
        (
            "DropBot connected on COM6",
            SEVERITY_SUCCESS,
            "Firmware 2.4.1, 120 channels.",
        ),
    ),
    CHIP_INSERTED_TOPIC: (
        ("Chip detected", SEVERITY_SUCCESS, "The protocol continues from step 3."),
        None,
    ),
    RESTART_TOPIC: (
        ("MicroDrop would restart now", SEVERITY_INFO, "Not in the demo."),
        None,
    ),
}
