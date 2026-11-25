# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Small human-readable JSON state files: read as "no state" when missing
or unreadable, written whole and atomically (a temporary file, then
replaced), indented with keys in a stable order so they diff and read
easily by hand. Qt-free."""

# Standard library imports.
import json
from pathlib import Path

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def read_json_state(path):
    """The dict saved at ``path``; None when there is none. A file that
    cannot be read or is not a JSON object logs one warning and counts as
    none: state is never worth a crash."""
    path = Path(path)

    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))

    except (OSError, ValueError) as error:
        logger.warning(f"State file {path} could not be read ({error}); ignored")

        return None

    if not isinstance(data, dict):
        logger.warning(f"State file {path} does not hold an object; ignored")

        return None

    return data


def write_json_state(path, data):
    """Save ``data`` (a dict) at ``path``, replacing the file whole; its
    folder is made on the first write. Returns whether it was saved; a
    failure is logged."""
    path = Path(path)
    partial = path.with_name(f"{path.name}.tmp")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        partial.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        partial.replace(path)

    except OSError as error:
        logger.error(f"Could not save {path}: {error}")

        return False

    return True


def move_state_file(old_path, new_path):
    """Move a state file from where it used to live, once: only while the
    old file exists and the new one does not, so there are never two
    copies and the old place is not looked at again afterwards."""
    old_path, new_path = Path(old_path), Path(new_path)

    if not old_path.is_file() or new_path.exists():
        return

    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.replace(new_path)
        logger.info(f"Moved {old_path} to {new_path}")

    except OSError as error:
        logger.warning(f"Could not move {old_path} to {new_path}: {error}")
