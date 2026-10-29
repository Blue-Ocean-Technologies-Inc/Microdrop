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
import json
import os
import pickle
from pathlib import Path

# Enthought library imports.
from pyface.tasks.api import TaskWindowLayout
from traits.api import Dict, Directory, HasTraits, List, Str

# Local imports.
from ..consts import (
    DEFAULT_PRESET_STEM,
    DEFAULT_SHORTCUT_KEYS,
    DEFAULT_SHORTCUT_MODIFIER,
    INVALID_PRESET_NAME_CHARACTERS,
    PRESET_FILE_SUFFIX,
    RESERVED_PRESET_NAMES,
    SHORTCUTS_FILENAME,
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

    #: Preset name -> key sequence (Qt portable text) applying it, for the
    #: listed presets that have one.
    shortcuts = Dict(Str, Str)

    def refresh(self):
        """Rescan ``directory``, listing every preset that loads."""
        names = [
            name
            for name in self.saved_names()
            if self._read(self._path_for(name)) is not None
        ]

        self.shortcuts = {
            name: shortcut
            for name, shortcut in self._read_shortcuts().items()
            if name in names
        }
        self.presets = sorted(names, key=str.casefold)

    def has_preset(self, name):
        """Return whether a preset file named ``name`` is already on disk."""
        return self._path_for(name).exists()

    def saved_names(self):
        """Return the name of every preset file on disk, readable or not."""
        directory = Path(self.directory)

        if not directory.is_dir():
            return []

        return [path.stem for path in directory.glob(f"*{PRESET_FILE_SUFFIX}")]

    def next_default_name(self):
        """Return ``<stem>-N`` for the smallest N not already saved."""
        number = 1

        while self.has_preset(f"{DEFAULT_PRESET_STEM}-{number}"):
            number += 1

        return f"{DEFAULT_PRESET_STEM}-{number}"

    def next_default_shortcut(self):
        """Return ``<modifier>+<key>`` for the first default key no preset
        uses, or "" once every default key is taken."""
        taken = set(self._saved_preset_shortcuts().values())

        for key in DEFAULT_SHORTCUT_KEYS:
            shortcut = f"{DEFAULT_SHORTCUT_MODIFIER}+{key}"

            if shortcut not in taken:
                return shortcut

        return ""

    def shortcut_for(self, name):
        """Return the key sequence applying preset ``name``, or ""."""
        return self.shortcuts.get(name.strip(), "")

    def save(self, name, layout, protocol, shortcut=""):
        """Pickle ``layout`` as preset ``name`` with key sequence
        ``shortcut`` ("" for none), replacing any preset of that name.

        Raises ``ValueError`` when ``name`` breaks the naming rule.
        """
        error = preset_name_error(name)

        if error:
            raise ValueError(error)

        name = name.strip()
        path = self._path_for(name)

        _write_atomically(path, pickle.dumps(layout, protocol=protocol))
        self._write_preset_shortcut(name, shortcut)
        logger.info(f"Saved layout preset '{name}' ({shortcut or 'no shortcut'})")

        self.refresh()

    def delete(self, name):
        """Remove preset ``name`` and its shortcut; warn if it is unknown."""
        name = name.strip()

        if not self.has_preset(name):
            logger.warning(f"Cannot delete unknown layout preset '{name}'")

            return

        self._path_for(name).unlink()
        self._write_shortcuts(self._saved_preset_shortcuts())
        logger.info(f"Deleted layout preset '{name}'")

        self.refresh()

    def rename(self, old_name, new_name):
        """Rename preset ``old_name`` to ``new_name``, carrying its shortcut.

        Raises ``ValueError`` when ``old_name`` is unknown, ``new_name``
        breaks the naming rule, or another preset already has that name.
        """
        error = preset_name_error(new_name)

        if error:
            raise ValueError(error)

        old_name = old_name.strip()
        new_name = new_name.strip()
        old_path = self._path_for(old_name)
        new_path = self._path_for(new_name)

        if not self.has_preset(old_name):
            raise ValueError(f"There is no layout preset named '{old_name}'.")

        if new_name == old_name:
            return

        # A case-only rename on a case-insensitive filesystem finds its own
        # file under the new name; that is no collision.
        if new_path.exists() and not old_path.samefile(new_path):
            raise ValueError(f"A layout preset named '{new_name}' already exists.")

        shortcuts = self._saved_preset_shortcuts()
        shortcut = shortcuts.pop(old_name, "")

        if shortcut:
            shortcuts[new_name] = shortcut

        os.replace(old_path, new_path)
        self._write_shortcuts(shortcuts)
        logger.info(f"Renamed layout preset '{old_name}' to '{new_name}'")

        self.refresh()

    def set_shortcut(self, name, shortcut):
        """Give preset ``name`` key sequence ``shortcut`` ("" removes it);
        warn if the preset is unknown."""
        name = name.strip()

        if not self.has_preset(name):
            logger.warning(f"Cannot set the shortcut of unknown layout preset '{name}'")

            return

        self._write_preset_shortcut(name, shortcut)
        logger.info(f"Layout preset '{name}' shortcut: {shortcut or 'none'}")

        self.refresh()

    def load(self, name):
        """Return the ``TaskWindowLayout`` saved as ``name``, or None."""
        return self._read(self._path_for(name))

    def _path_for(self, name):
        return Path(self.directory) / f"{name.strip()}{PRESET_FILE_SUFFIX}"

    def _write_preset_shortcut(self, name, shortcut):
        """Record ``shortcut`` ("" for none) as preset ``name``'s."""
        shortcuts = self._saved_preset_shortcuts()
        shortcuts.pop(name, None)

        if shortcut:
            shortcuts[name] = shortcut

        self._write_shortcuts(shortcuts)

    def _write_shortcuts(self, shortcuts):
        _write_atomically(
            Path(self.directory) / SHORTCUTS_FILENAME,
            json.dumps(shortcuts, indent=2, sort_keys=True).encode("utf-8"),
        )

    def _saved_preset_shortcuts(self):
        """Return the shortcuts file's entries whose preset is on disk."""
        return {
            name: shortcut
            for name, shortcut in self._read_shortcuts().items()
            if self.has_preset(name)
        }

    def _read_shortcuts(self):
        """Return the shortcuts file's ``{name: key sequence}``, or {}."""
        path = Path(self.directory) / SHORTCUTS_FILENAME

        if not path.is_file():
            return {}

        try:
            shortcuts = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A damaged file only costs the shortcuts, never the presets.
            logger.exception(f"Could not read layout preset shortcuts {path}")

            return {}

        if not isinstance(shortcuts, dict):
            logger.error(f"Layout preset shortcuts {path} is not a JSON object")

            return {}

        return {
            name: shortcut
            for name, shortcut in shortcuts.items()
            if isinstance(shortcut, str) and shortcut
        }

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


def _write_atomically(path, content):
    """Write ``content`` (bytes) to ``path`` aside, then swap it in, so a
    failed write never truncates the file being replaced."""
    partial_path = path.with_name(f"{path.name}.partial")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial_path.write_bytes(content)

    os.replace(partial_path, path)
