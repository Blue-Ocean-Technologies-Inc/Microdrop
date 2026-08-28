# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Live interface scaling through the display server.

Qt cannot rescale a running interface (QT_SCALE_FACTOR is sampled once
in the QGuiApplication constructor), but the portable rig's X server
can: ``xrandr --scale`` re-renders the whole desktop at a new logical
size instantly. 80% interface scale = xrandr factor 1.25: the panel
gains logical room and everything on it shrinks, so more panes fit.

The transform is instrument-wide by nature — on the dedicated rig the
app effectively is the desktop. Qt-free by design.
"""

import os
import shutil
import subprocess

from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Per-command timeout, so a wedged X server cannot hang the GUI thread.
XRANDR_TIMEOUT_S = 10

#: The connected output, discovered once — the rig does not hot-swap
#: its panel.
_output_cache = None


def live_scaling_available():
    """Whether the display server can rescale the running interface."""
    return bool(
        os.name == "posix"
        and os.environ.get("DISPLAY")
        and shutil.which("xrandr")
        and _connected_output()
    )


def apply_live_scale(percent):
    """Rescale the desktop so the interface renders at ``percent`` size.

    Returns True when the display server accepted the new scale.
    """
    output = _connected_output()
    if output is None:
        return False

    factor = 100 / percent
    try:
        result = subprocess.run(
            ["xrandr", "--output", output, "--scale", f"{factor:g}x{factor:g}"],
            capture_output=True,
            text=True,
            timeout=XRANDR_TIMEOUT_S,
        )
    except Exception as e:
        logger.warning(f"Could not rescale output {output}: {e}")
        return False

    if result.returncode != 0:
        logger.warning(
            f"xrandr refused scale {factor:g} on {output}: {result.stderr.strip()}"
        )
        return False

    logger.info(
        f"Interface scale {percent}% applied live (xrandr {output} scale {factor:g})"
    )
    return True


def _connected_output():
    """The name of the (single) connected output, or None."""
    global _output_cache
    if _output_cache is not None:
        return _output_cache

    try:
        result = subprocess.run(
            ["xrandr"], capture_output=True, text=True, timeout=XRANDR_TIMEOUT_S
        )
    except Exception as e:
        logger.debug(f"xrandr query failed: {e}")
        return None

    for line in result.stdout.splitlines():
        words = line.split()
        if len(words) > 1 and words[1] == "connected":
            _output_cache = words[0]
            return _output_cache

    return None
