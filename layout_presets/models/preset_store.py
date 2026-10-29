# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The saved window-layout presets: one pickled ``TaskWindowLayout`` per
file in a directory, the file stem being the preset's name."""

# Standard library imports.
import os
import pickle
from pathlib import Path

# Enthought library imports.
from pyface.tasks.api import TaskWindowLayout
from traits.api import Directory, HasTraits, List, Str

# Local imports.
from ..consts import (
    DEFAULT_PRESET_STEM,
    INVALID_PRESET_NAME_CHARACTERS,
    PRESET_FILE_SUFFIX,
    RESERVED_PRESET_NAMES,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def preset_name_error(name):
    """Return why ``name`` cannot name a preset, or "" when it can.

    The single naming rule: the stripped name becomes a file stem, so it
    must be non-empty and safe on every platform the app runs on.
    """
    name = name.strip()

    if not name:
        return "Enter a name for the preset."

    invalid_characters = sorted(set(name) & set(INVALID_PRESET_NAME_CHARACTERS))

    if invalid_characters:
        return f"A preset name cannot contain {' '.join(invalid_characters)}"

    if any(ord(character) < 32 for character in name):
        return "A preset name cannot contain control characters."

    if name.endswith("."):
        return "A preset name cannot end with a period."

    if name.upper() in RESERVED_PRESET_NAMES:
        return f"'{name}' is reserved by the operating system."

    return ""


def is_valid_preset_name(name):
    """Return whether ``name`` (once stripped) can name a preset."""
    return not preset_name_error(name)


class PresetStore(HasTraits):
    """The layout presets saved in ``directory``."""

    #: Folder holding one pickled ``TaskWindowLayout`` per preset.
    directory = Directory()

    #: SOURCE OF TRUTH for the menu — sorted names of the readable presets.
    presets = List(Str)

    def refresh(self):
        """Rescan ``directory``, listing every preset that loads."""
        directory = Path(self.directory)
        names = []

        if directory.is_dir():
            for path in directory.glob(f"*{PRESET_FILE_SUFFIX}"):
                if self._read(path) is not None:
                    names.append(path.stem)

        self.presets = sorted(names, key=str.casefold)

    def has_preset(self, name):
        """Return whether a preset file named ``name`` is already on disk."""
        return self._path_for(name).exists()

    def next_default_name(self):
        """Return ``<stem>-N`` for the smallest N not already saved."""
        number = 1

        while self.has_preset(f"{DEFAULT_PRESET_STEM}-{number}"):
            number += 1

        return f"{DEFAULT_PRESET_STEM}-{number}"

    def save(self, name, layout, protocol):
        """Pickle ``layout`` as preset ``name``, replacing any of that name.

        Raises ``ValueError`` when ``name`` breaks the naming rule.
        """
        error = preset_name_error(name)

        if error:
            raise ValueError(error)

        path = self._path_for(name)
        partial_path = path.with_name(f"{path.name}.partial")
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write aside, then swap in, so a failed write never truncates the
        # preset being overwritten.
        with open(partial_path, "wb") as file:
            pickle.dump(layout, file, protocol=protocol)

        os.replace(partial_path, path)
        logger.info(f"Saved layout preset '{name.strip()}' to {path}")

        self.refresh()

    def load(self, name):
        """Return the ``TaskWindowLayout`` saved as ``name``, or None."""
        return self._read(self._path_for(name))

    def _path_for(self, name):
        return Path(self.directory) / f"{name.strip()}{PRESET_FILE_SUFFIX}"

    def _read(self, path):
        """Unpickle the layout at ``path``; log and return None on failure."""

        try:
            with open(path, "rb") as file:
                layout = pickle.load(file)
        except Exception:
            # Any unpickling failure (truncated file, a class pyface renamed
            # since the preset was saved) only costs this one preset.
            logger.exception(f"Could not read layout preset {path}")

            return None

        if not isinstance(layout, TaskWindowLayout):
            logger.error(
                f"Layout preset {path} holds a {type(layout).__name__}, "
                f"not a TaskWindowLayout"
            )

            return None

        return layout
