# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The texts of the updates dialogs: each names what the user must know."""

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils.source_update_startup import SKIP_GIT_UPDATE_ENV_VAR
from microdrop_utils.source_version import DEVELOPMENT, MANAGED, NO_GIT

# Local imports.
from ..messages import (
    close_message,
    forced_pull_warning,
    newer_version_notice,
    no_panel_warning,
    plain_confirmation,
    skip_variable_line,
    state_line,
)

COMMANDS = 'cd "C:\\MicroDrop <src>"\ngit checkout main\ngit pull'
UNSET_COMMAND = "reg delete HKCU\\Environment /v MICRODROP_SKIP_GIT_UPDATE /f"


@pytest.mark.parametrize("drops_unreleased", [True, False])
@pytest.mark.parametrize("frontend_only", [True, False])
def test_plain_confirmation(drops_unreleased, frontend_only):
    text = plain_confirmation("v1.46.0", drops_unreleased, frontend_only)

    assert "v1.46.0" in text
    assert ("unreleased" in text) == drops_unreleased
    assert ("restart the backend" in text.lower()) == frontend_only


def test_no_panel_warning():
    text = no_panel_warning("v1.40.0", COMMANDS)

    assert "v1.40.0" in text
    assert "no Updates panel" in text
    assert "Setup &amp; Launcher" in text
    # Interpolated commands are escaped, never taken as markup.
    assert "&lt;src&gt;" in text
    assert "<src>" not in text


def test_forced_pull_warning():
    text = forced_pull_warning(
        "v1.30.0", COMMANDS, SKIP_GIT_UPDATE_ENV_VAR, UNSET_COMMAND
    )

    assert "v1.30.0" in text
    assert "no Updates panel" in text
    assert "Setup &amp; Launcher" in text
    assert "checks out main" in text
    assert "pulls" in text
    assert "next start" in text
    assert SKIP_GIT_UPDATE_ENV_VAR in text
    assert UNSET_COMMAND in text
    assert "reopen" in text.lower()


def test_close_message():
    text = close_message("v1.46.0")

    assert "v1.46.0" in text
    assert "start MicroDrop again" in text


def test_state_line_is_plain_text():
    assert state_line(MANAGED, "") == ""
    # Shown in a plain label: a branch name appears verbatim, never escaped.
    assert "branch R&D" in state_line(DEVELOPMENT, "branch R&D")
    assert "&amp;" not in state_line(DEVELOPMENT, "branch R&D")
    assert "local changes" in state_line(DEVELOPMENT, "local changes")
    assert "git is not installed" in state_line(NO_GIT, "git is not installed")


def test_skip_variable_line_is_plain_text():
    text = skip_variable_line(SKIP_GIT_UPDATE_ENV_VAR)

    assert "Automatic updates are off" in text
    assert SKIP_GIT_UPDATE_ENV_VAR in text
    assert "<" not in text


def test_newer_version_notice():
    assert newer_version_notice("v1.47.0") == "MicroDrop v1.47.0 is available."
