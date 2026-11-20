# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""user_environment: the permanent per-user variable in the shell profile and
in the Windows registry. Never touches this machine's real profile, registry
or environment — the POSIX tests use ``tmp_path`` as home, the Windows tests a
fake ``winreg``."""

# Standard library imports.
import os
import sys
from contextlib import contextmanager
from pathlib import Path

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils import user_environment
from microdrop_utils.user_environment import (
    manual_unset_command,
    set_user_environment_variable,
    unset_user_environment_variable,
    user_environment_variable,
)

#: Made up, so a failing test can never leave a real setting behind.
NAME = "MICRODROP_TEST_VARIABLE"

MARKED_LINE = f"export {NAME}='1'  # added by MicroDrop\n"


class FakeWinreg:
    """Stand in for the slice of ``winreg`` the module uses, over a dict."""

    HKEY_CURRENT_USER = "HKEY_CURRENT_USER"
    KEY_READ = 0x20019
    KEY_SET_VALUE = 0x0002
    REG_SZ = 1
    REG_EXPAND_SZ = 2
    REG_DWORD = 4

    def __init__(self):
        #: name -> (value, type) under HKEY_CURRENT_USER\Environment.
        self.values = {}

        #: Raised by every value access when set, to simulate a broken key.
        self.failure = None

    @contextmanager
    def OpenKey(self, key, sub_key, reserved=0, access=KEY_READ):
        assert (key, sub_key) == (self.HKEY_CURRENT_USER, "Environment")

        yield self

    CreateKeyEx = OpenKey

    def _check(self):
        if self.failure is not None:
            raise self.failure

    def SetValueEx(self, key, name, reserved, value_type, value):
        self._check()
        self.values[name] = (value, value_type)

    def QueryValueEx(self, key, name):
        self._check()

        if name not in self.values:
            raise FileNotFoundError(2, "The system cannot find the file specified")

        return self.values[name]

    def DeleteValue(self, key, name):
        self._check()

        if name not in self.values:
            raise FileNotFoundError(2, "The system cannot find the file specified")

        del self.values[name]


@pytest.fixture(autouse=True)
def isolated_variable(monkeypatch):
    """Start every test without ``NAME`` and remove it again afterwards.

    delenv of an absent name records nothing to undo, so a value the module
    sets would outlive the test; setenv first makes pytest record the
    absence."""
    monkeypatch.setenv(NAME, "")
    monkeypatch.delenv(NAME)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Make the user a Linux user whose home is ``tmp_path``."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    return tmp_path


@pytest.fixture
def mac_home(home, monkeypatch):
    """Make the user a macOS user whose home is ``tmp_path``."""
    monkeypatch.setattr(sys, "platform", "darwin")

    return home


@pytest.fixture
def broadcasts(monkeypatch):
    """Record the WM_SETTINGCHANGE broadcasts made, one entry per call."""
    calls = []

    monkeypatch.setattr(
        user_environment, "_send_setting_change", lambda: calls.append(1)
    )

    return calls


@pytest.fixture
def fake_winreg(monkeypatch, broadcasts):
    """Make the user a Windows user whose registry is a ``FakeWinreg``."""
    registry = FakeWinreg()

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(user_environment, "_winreg_module", lambda: registry)

    return registry


@pytest.fixture
def warnings(monkeypatch):
    """Record the module's logged warnings."""
    messages = []

    monkeypatch.setattr(user_environment.logger, "warning", messages.append)

    return messages


def test_posix_set_appends_marked_line_and_keeps_other_lines(home):
    # CRLF and a missing final newline must both survive untouched.
    original = b"# my settings\r\nexport PATH=/opt/bin:$PATH"
    (home / ".profile").write_bytes(original)

    set_user_environment_variable(NAME, "1")

    assert (home / ".profile").read_bytes() == original + b"\n" + MARKED_LINE.encode()


def test_posix_set_creates_missing_profile(home):
    set_user_environment_variable(NAME, "1")

    assert (home / ".profile").read_text() == MARKED_LINE


def test_posix_set_twice_leaves_one_line(home):
    (home / ".profile").write_text("umask 022\n")

    set_user_environment_variable(NAME, "1")
    set_user_environment_variable(NAME, "2")

    assert (home / ".profile").read_text() == (
        f"umask 022\nexport {NAME}='2'  # added by MicroDrop\n"
    )


def test_posix_set_keeps_the_replaced_line_ending(home):
    (home / ".profile").write_bytes(
        f"export {NAME}='1'  # added by MicroDrop\r\numask 022\r\n".encode()
    )

    set_user_environment_variable(NAME, "2")

    assert (home / ".profile").read_bytes() == (
        f"export {NAME}='2'  # added by MicroDrop\r\numask 022\r\n".encode()
    )


def test_posix_unset_removes_only_the_marked_line(home):
    others_before = "umask 022\n"
    others_after = (
        f"export {NAME}=9\n"
        "export MICRODROP_OTHER_VARIABLE='1'  # added by MicroDrop\n"
        "alias ll='ls -l'"
    )
    (home / ".profile").write_text(others_before + MARKED_LINE + others_after)

    unset_user_environment_variable(NAME)

    assert (home / ".profile").read_text() == others_before + others_after


def test_posix_unset_without_profile_is_quiet(home):
    unset_user_environment_variable(NAME)

    assert not (home / ".profile").exists()


def test_posix_read_back(home):
    assert user_environment_variable(NAME) is None

    set_user_environment_variable(NAME, "1")

    assert user_environment_variable(NAME) == "1"

    unset_user_environment_variable(NAME)

    assert user_environment_variable(NAME) is None


def test_posix_read_ignores_unmarked_lines(home):
    (home / ".profile").write_text(f"export {NAME}=1\n")

    assert user_environment_variable(NAME) is None


def test_posix_read_failure_is_none(home, warnings):
    (home / ".profile").mkdir()

    assert user_environment_variable(NAME) is None
    assert warnings


def test_read_without_a_home_is_none(home, monkeypatch, warnings):
    def no_home(cls):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", classmethod(no_home))

    assert user_environment_variable(NAME) is None
    assert warnings


def test_read_with_invalid_name_is_none(home, warnings):
    assert user_environment_variable("MY-VAR") is None
    assert warnings


def test_posix_write_failure_propagates(home):
    (home / ".profile").mkdir()

    with pytest.raises(OSError):
        set_user_environment_variable(NAME, "1")

    assert NAME not in os.environ


def test_posix_failed_replace_leaves_profile_intact(home, monkeypatch):
    original = b"umask 022\r\nexport PATH=/opt/bin:$PATH"
    (home / ".profile").write_bytes(original)

    def failing_replace(source, destination):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(user_environment.os, "replace", failing_replace)

    with pytest.raises(PermissionError):
        set_user_environment_variable(NAME, "1")

    assert (home / ".profile").read_bytes() == original
    assert [path.name for path in home.iterdir()] == [".profile"]
    assert NAME not in os.environ


def test_mac_uses_zprofile(mac_home):
    set_user_environment_variable(NAME, "1")

    assert (mac_home / ".zprofile").read_text() == MARKED_LINE
    assert not (mac_home / ".profile").exists()
    assert user_environment_variable(NAME) == "1"

    unset_user_environment_variable(NAME)

    assert (mac_home / ".zprofile").read_text() == ""
    assert user_environment_variable(NAME) is None


@pytest.mark.parametrize("name", ["", "1ST", "MY-VAR", "X;rm -rf ~", "X Y"])
def test_invalid_name_is_rejected(home, name):
    with pytest.raises(ValueError):
        set_user_environment_variable(name, "1")

    with pytest.raises(ValueError):
        unset_user_environment_variable(name)

    with pytest.raises(ValueError):
        manual_unset_command(name)

    assert not (home / ".profile").exists()


@pytest.mark.parametrize("value", ["1\nrm -rf ~", "1\r", "it's", "1\0"])
def test_value_that_could_escape_the_profile_line_is_rejected(home, value):
    with pytest.raises(ValueError):
        set_user_environment_variable(NAME, value)

    assert not (home / ".profile").exists()
    assert NAME not in os.environ


def test_shell_syntax_in_a_value_stays_literal(home):
    set_user_environment_variable(NAME, "$(touch pwned) `id`; x")

    assert (home / ".profile").read_text() == (
        f"export {NAME}='$(touch pwned) `id`; x'  # added by MicroDrop\n"
    )
    assert user_environment_variable(NAME) == "$(touch pwned) `id`; x"


def test_windows_set_read_unset_roundtrip(fake_winreg, broadcasts):
    assert user_environment_variable(NAME) is None

    set_user_environment_variable(NAME, "1")

    assert fake_winreg.values[NAME] == ("1", FakeWinreg.REG_SZ)
    assert user_environment_variable(NAME) == "1"

    unset_user_environment_variable(NAME)

    assert NAME not in fake_winreg.values
    assert user_environment_variable(NAME) is None
    assert len(broadcasts) == 2


def test_windows_unset_absent_value_is_quiet(fake_winreg):
    unset_user_environment_variable(NAME)

    assert fake_winreg.values == {}


def test_windows_read_failure_is_none(fake_winreg, warnings):
    fake_winreg.values[NAME] = ("1", FakeWinreg.REG_SZ)
    fake_winreg.failure = PermissionError(5, "Access is denied")

    assert user_environment_variable(NAME) is None
    assert warnings


def test_windows_read_only_string_values(fake_winreg):
    fake_winreg.values[NAME] = (1, FakeWinreg.REG_DWORD)

    assert user_environment_variable(NAME) is None

    fake_winreg.values[NAME] = ("%USERPROFILE%", FakeWinreg.REG_EXPAND_SZ)

    assert user_environment_variable(NAME) == "%USERPROFILE%"


def test_windows_write_failure_propagates(fake_winreg, broadcasts):
    fake_winreg.failure = PermissionError(5, "Access is denied")

    with pytest.raises(PermissionError):
        set_user_environment_variable(NAME, "1")

    assert NAME not in os.environ
    assert broadcasts == []


def test_windows_broadcast_failure_is_a_warning(fake_winreg, monkeypatch, warnings):
    def failing_send():
        raise OSError(1460, "This operation returned because the timeout period")

    monkeypatch.setattr(user_environment, "_send_setting_change", failing_send)

    set_user_environment_variable(NAME, "1")

    assert fake_winreg.values[NAME] == ("1", FakeWinreg.REG_SZ)
    assert os.environ[NAME] == "1"
    assert warnings


def test_set_and_unset_update_os_environ(home):
    set_user_environment_variable(NAME, "1")

    assert os.environ[NAME] == "1"

    unset_user_environment_variable(NAME)

    assert NAME not in os.environ


@pytest.mark.parametrize(
    "platform, command",
    [
        ("win32", f"reg delete HKCU\\Environment /v {NAME} /f"),
        (
            "linux",
            f"sed -i.bak '/^export {NAME}=.*# added by MicroDrop$/d' ~/.profile",
        ),
        (
            "darwin",
            f"sed -i.bak '/^export {NAME}=.*# added by MicroDrop$/d' ~/.zprofile",
        ),
    ],
)
def test_manual_unset_command_per_platform(monkeypatch, platform, command):
    monkeypatch.setattr(sys, "platform", platform)

    assert manual_unset_command(NAME) == command
