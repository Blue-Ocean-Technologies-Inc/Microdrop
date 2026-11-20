# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the shared application home and early preference reads."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
import pytest

# Enthought library imports.
from traits.etsconfig.api import ETSConfig

# Microdrop utils imports.
from microdrop_utils import application_home
from microdrop_utils.application_home import (
    PREFERENCES_FILENAME,
    configure_application_home,
    preferences_file_path,
    read_bool_preference,
)

AUTO_UPDATE_PATH = "microdrop.app_updates.auto_update"


# The private ETSConfig fields are patched, not the properties: reading a
# property to save it would compute and cache the real data folder.
@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(application_home, "configure_application_home", lambda: None)
    monkeypatch.setattr(ETSConfig, "_application_home", str(tmp_path))

    return tmp_path


def _write_preferences(home, text):
    (home / PREFERENCES_FILENAME).write_text(text, encoding="utf-8")


def test_missing_file_gives_default(home):
    assert read_bool_preference(AUTO_UPDATE_PATH, True) is True
    assert read_bool_preference(AUTO_UPDATE_PATH, False) is False


def test_reads_false(home):
    _write_preferences(home, "[microdrop.app_updates]\nauto_update = False\n")

    assert read_bool_preference(AUTO_UPDATE_PATH, True) is False


def test_reads_true_case_insensitively(home):
    _write_preferences(home, "[microdrop.app_updates]\nauto_update = tRuE\n")

    assert read_bool_preference(AUTO_UPDATE_PATH, False) is True


def test_missing_key_gives_default(home):
    _write_preferences(home, "[microdrop.app_updates]\nother_key = False\n")

    assert read_bool_preference(AUTO_UPDATE_PATH, True) is True


def test_garbage_value_gives_default(home):
    _write_preferences(home, "[microdrop.app_updates]\nauto_update = maybe\n")

    assert read_bool_preference(AUTO_UPDATE_PATH, True) is True


def test_malformed_file_gives_default_and_does_not_raise(home):
    _write_preferences(home, "[[[\x00")

    assert read_bool_preference(AUTO_UPDATE_PATH, True) is True


def test_unlocatable_preferences_file_gives_default_and_does_not_raise(
    home, monkeypatch
):
    def fail_to_locate():
        raise OSError("no home folder")

    monkeypatch.setattr(application_home, "preferences_file_path", fail_to_locate)

    assert read_bool_preference(AUTO_UPDATE_PATH, True) is True


def test_preferences_file_path_is_under_application_home(home):
    assert preferences_file_path() == Path(home) / PREFERENCES_FILENAME


def test_configure_application_home_sets_the_microdrop_folders(tmp_path, monkeypatch):
    for field in ("_company", "_user_data", "_application_home"):
        monkeypatch.setattr(ETSConfig, field, None)

    monkeypatch.setattr(ETSConfig, "_application_data", str(tmp_path))

    configure_application_home()
    first = (ETSConfig.company, ETSConfig.user_data, ETSConfig.application_home)
    configure_application_home()

    assert first == (
        "Sci-Bots",
        str(Path.home() / "Documents" / "Sci-Bots" / "Microdrop"),
        str(tmp_path / "Microdrop"),
    )
    assert (ETSConfig.company, ETSConfig.user_data, ETSConfig.application_home) == (
        first
    )
