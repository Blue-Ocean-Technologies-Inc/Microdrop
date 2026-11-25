# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The device viewer's kinds of notification (NOTIFICATION_CATEGORIES) and
what their cards share. Re-exported from ``device_viewer.consts``, which
readers import them from."""

# Microdrop package imports.
from notifications.consts import TONE_SOFT, NotificationCategorySpec

# The device viewer's package, as device_viewer.consts names it.
PKG = ".".join(__name__.split(".")[:-1])

#: What restoring a camera's alignment did on a camera switch or a device
#: load: restored, applied a default, held back, or nothing saved.
CAMERA_ALIGNMENT_CATEGORY_ID = f"{PKG}.camera_alignment"

#: A photo captured or a video saved, and a capture that failed.
CAMERA_CAPTURES_CATEGORY_ID = f"{PKG}.camera_captures"

#: Outside a protocol run, a photo saved within this many seconds of the
#: previous one, into the same folder, updates that photo's card.
CAPTURE_SESSION_WINDOW_S = 5 * 60

#: Reminders to keep the DropBot calibrated and self-tested: a calibration
#: missing or old (here), a self test never run or old (dropbot_tools_menu,
#: which reuses this id).
DROPBOT_MAINTENANCE_CATEGORY_ID = f"{PKG}.dropbot_maintenance"

NOTIFICATION_CATEGORY_SPECS = [
    NotificationCategorySpec(
        id=CAMERA_ALIGNMENT_CATEGORY_ID,
        group="Camera",
        label="Alignment",
        description="A camera's alignment restored, or none saved for it.",
        tone=TONE_SOFT,
    ),
    NotificationCategorySpec(
        id=CAMERA_CAPTURES_CATEGORY_ID,
        group="Camera",
        label="Captures",
        description="Photos captured and videos saved, or a capture that failed.",
        tone=TONE_SOFT,
    ),
    NotificationCategorySpec(
        id=DROPBOT_MAINTENANCE_CATEGORY_ID,
        group="DropBot",
        label="Maintenance reminders",
        description="No calibration saved or an old one; a self test never "
        "run or an old one.",
        tone=TONE_SOFT,
    ),
]
