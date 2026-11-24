# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Notification chimes shipped with the style package, by name; made by
``make_chimes`` in this folder."""

# Standard library imports.
from pathlib import Path

#: Where the sounds are.
SOUNDS_DIR = Path(__file__).parent

#: A soft single note, for info, success and news.
CHIME_GENTLE = SOUNDS_DIR / "chime_gentle.wav"

#: A short rising pair, for warnings, errors and Needs attention.
CHIME_ALERT = SOUNDS_DIR / "chime_alert.wav"

#: Three even beeps, longer and stronger, for something finished.
CHIME_COMPLETION = SOUNDS_DIR / "chime_completion.wav"
