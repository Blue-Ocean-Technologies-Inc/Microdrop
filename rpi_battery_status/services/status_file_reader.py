# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Locate and read the rpi-battery-monitor daemon's status file."""

# Standard library imports.
import json
import os
from pathlib import Path

# Local imports.
from ..consts import (
    FALLBACK_RUNTIME_DIR_TEMPLATE,
    STATUS_DIR_NAME,
    STATUS_FILE_ENV_VAR,
    STATUS_FILE_NAME,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def status_file_path():
    """Return the path the daemon writes its status snapshot to.

    The env override wins, then ``$XDG_RUNTIME_DIR``, then the daemon's
    per-user ``/tmp`` fallback.
    """
    override = os.environ.get(STATUS_FILE_ENV_VAR)

    if override:
        return Path(override)

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")

    if not runtime_dir:
        # os.getuid is POSIX-only. No daemon runs on Windows; the path
        # there never exists and reads as unavailable.
        uid = os.getuid() if hasattr(os, "getuid") else "unknown"
        runtime_dir = FALLBACK_RUNTIME_DIR_TEMPLATE.format(uid=uid)

    return Path(runtime_dir) / STATUS_DIR_NAME / STATUS_FILE_NAME


def read_snapshot(path):
    """Return the status snapshot at ``path`` as a dict, or None.

    A missing file is the normal state wherever the daemon does not run;
    an unreadable or malformed one is logged and also returns None.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        logger.debug(f"No battery status file at {path}")
        return None
    except OSError as e:
        logger.warning(f"Could not read battery status file {path}: {e}")
        return None

    # ValueError covers both bad JSON and undecodable bytes.
    try:
        snapshot = json.loads(raw)
    except ValueError as e:
        logger.warning(f"Malformed battery status file {path}: {e}")
        return None

    if not isinstance(snapshot, dict):
        logger.warning(f"Battery status file {path} holds no JSON object")
        return None

    return snapshot
