# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Permanent per-user environment variables, seen by every program the user
starts from now on.

On Windows the variable lives in ``HKEY_CURRENT_USER\\Environment``; elsewhere
it is one marked line of ``~/.profile``,
``export <name>='<value>'  # added by MicroDrop``, and no other line of that
file is ever changed. Setting and unsetting also update this process's
``os.environ``.

This module is Qt-free. Writes raise the original OSError; reads never raise
and answer None instead.
"""

# Standard library imports.
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Ends every ``~/.profile`` line this module owns.
PROFILE_MARKER = "# added by MicroDrop"

#: The registry key, under HKEY_CURRENT_USER, holding the user's variables.
_ENVIRONMENT_KEY = "Environment"

#: SendMessageTimeoutW arguments for telling running programs (Explorer
#: above all) that the user's environment changed.
_HWND_BROADCAST = 0xFFFF
_WM_SETTINGCHANGE = 0x001A
_SMTO_ABORTIFHUNG = 0x0002
_BROADCAST_TIMEOUT_MS = 5000

#: A new ``~/.profile`` gets the usual mode of a dotfile.
_NEW_PROFILE_MODE = 0o644

_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _is_windows():
    # Read at call time, so tests can exercise either platform anywhere.
    return sys.platform == "win32"


def _winreg_module():
    """The ``winreg`` module — imported here, the one seam tests replace,
    because it exists only on Windows."""
    import winreg

    return winreg


def _check_name(name):
    if not _NAME_PATTERN.fullmatch(name):
        raise ValueError(f"Not a valid environment variable name: {name!r}")


def _check_value(value):
    # The value is written single-quoted into a shell file: a quote would end
    # the quoting and a line break would start a new command.
    if any(character in value for character in "'\r\n"):
        raise ValueError(
            f"An environment variable value may not contain a quote or a "
            f"line break: {value!r}"
        )


def _profile_path():
    # Through a symlink to its target, so a managed dotfile stays a symlink.
    return (Path.home() / ".profile").resolve()


def _marked_line_pattern(name):
    """Matches this module's line for ``name`` (without its line ending),
    capturing the value. Looser than the written form on purpose, like the
    ``sed`` line of ``manual_unset_command``."""
    return re.compile(
        rf"export {re.escape(name)}=(?:'(?P<quoted>[^']*)'|(?P<bare>\S*))\s*"
        rf"{re.escape(PROFILE_MARKER)}"
    )


def _read_profile_lines(path):
    """The lines of ``path`` with their own endings, or [] when it is absent.

    Read so that joining the lines rewrites the file byte for byte."""
    try:
        with open(path, encoding="utf-8", errors="surrogateescape", newline="") as f:
            text = f.read()
    except FileNotFoundError:
        return []

    # Split on "\n" only — str.splitlines also breaks on characters a shell
    # treats as ordinary text.
    return re.findall(r"[^\n]*\n|[^\n]+", text)


def _write_profile_lines(path, lines):
    """Replace ``path`` with ``lines``, so a crash leaves either the old file
    or the new one — never a truncated one."""
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        mode = _NEW_PROFILE_MODE

    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f"{path.name}.", suffix=".tmp"
    )

    try:
        with open(
            descriptor,
            "w",
            encoding="utf-8",
            errors="surrogateescape",
            newline="",
        ) as f:
            f.write("".join(lines))

        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)

        raise


def _set_in_profile(name, value):
    path = _profile_path()
    pattern = _marked_line_pattern(name)
    marked_line = f"export {name}='{value}'  {PROFILE_MARKER}\n"

    lines = []
    replaced = False

    for line in _read_profile_lines(path):
        if not pattern.fullmatch(line.rstrip("\r\n")):
            lines.append(line)
        elif not replaced:
            lines.append(marked_line)
            replaced = True

    if not replaced:
        # Never let the new line share the old last line.
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"

        lines.append(marked_line)

    _write_profile_lines(path, lines)


def _unset_in_profile(name):
    path = _profile_path()
    pattern = _marked_line_pattern(name)
    lines = _read_profile_lines(path)

    kept = [line for line in lines if not pattern.fullmatch(line.rstrip("\r\n"))]

    if kept != lines:
        _write_profile_lines(path, kept)


def _read_from_profile(name):
    pattern = _marked_line_pattern(name)

    for line in _read_profile_lines(_profile_path()):
        match = pattern.fullmatch(line.rstrip("\r\n"))

        if match:
            return match["quoted"] if match["quoted"] is not None else match["bare"]

    return None


def _broadcast_environment_change():
    """Tell running programs the user's environment changed, so programs
    they start next see it. A failure only means a sign-out is needed."""
    import ctypes
    from ctypes import wintypes

    # A private handle on user32, so these argtypes never leak into
    # ctypes.windll users elsewhere in the process.
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    send_message_timeout = user32.SendMessageTimeoutW
    send_message_timeout.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPCWSTR,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    send_message_timeout.restype = wintypes.LPARAM

    result = ctypes.c_size_t()

    sent = send_message_timeout(
        _HWND_BROADCAST,
        _WM_SETTINGCHANGE,
        0,
        _ENVIRONMENT_KEY,
        _SMTO_ABORTIFHUNG,
        _BROADCAST_TIMEOUT_MS,
        ctypes.byref(result),
    )

    if not sent:
        logger.warning(
            f"Broadcasting the environment change failed or timed out "
            f"(error {ctypes.get_last_error()}); programs started before "
            f"signing out again may not see it"
        )


def _set_in_registry(name, value):
    winreg = _winreg_module()

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, _ENVIRONMENT_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    _broadcast_environment_change()


def _unset_in_registry(name):
    winreg = _winreg_module()

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _ENVIRONMENT_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        # Already gone, which is what unsetting asks for.
        return

    _broadcast_environment_change()


def _read_from_registry(name):
    winreg = _winreg_module()

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _ENVIRONMENT_KEY, 0, winreg.KEY_READ
        ) as key:
            value, _value_type = winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return None

    return value


def user_environment_variable(name):
    """The persisted value of the user variable ``name``, or None when it is
    not set or cannot be read. ``os.environ`` is not consulted."""
    try:
        if _is_windows():
            return _read_from_registry(name)

        return _read_from_profile(name)
    except OSError as e:
        logger.warning(f"Could not read the user environment variable {name}: {e}")

        return None


def set_user_environment_variable(name, value):
    """Persist ``name=value`` for the user and set it in this process.

    Raises ValueError for a name that is not a plain identifier or a value
    holding a quote or line break, and the original OSError when the setting
    cannot be written."""
    _check_name(name)
    _check_value(value)

    if _is_windows():
        _set_in_registry(name, value)
    else:
        _set_in_profile(name, value)

    os.environ[name] = value


def unset_user_environment_variable(name):
    """Remove the user variable ``name`` and drop it from this process; quiet
    when it is not set. Raises the original OSError when the removal cannot
    be written."""
    _check_name(name)

    if _is_windows():
        _unset_in_registry(name)
    else:
        _unset_in_profile(name)

    os.environ.pop(name, None)


def manual_unset_command(name):
    """The one shell line that removes the user variable ``name`` by hand on
    this platform."""
    _check_name(name)

    if _is_windows():
        return f"reg delete HKCU\\Environment /v {name} /f"

    return f"sed -i '/^export {name}=.*{PROFILE_MARKER}$/d' ~/.profile"
