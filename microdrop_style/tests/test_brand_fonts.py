# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The brand font loader registers the font files it finds, once, and the
brand families fall back to the application font when absent."""

# Standard library imports.
import shutil

# Enthought library imports.
from pyface.qt.QtGui import QFontDatabase, QGuiApplication
from pyface.qt.QtWidgets import QApplication

# Microdrop style imports.
from microdrop_style import brand_fonts
from microdrop_style.font_paths import get_font_path


def test_a_font_file_in_the_folder_is_registered_once(tmp_path):
    QApplication.instance() or QApplication([])
    shutil.copy(get_font_path("inter"), tmp_path / "Stand-in.ttf")

    families = brand_fonts.register_brand_fonts(tmp_path)

    assert families == {"Inter"}
    assert "Inter" in QFontDatabase.families()
    assert brand_fonts.register_brand_fonts(tmp_path) is families


def test_a_missing_brand_family_falls_back_to_the_application_font(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(brand_fonts, "_is_available", lambda family: False)

    assert brand_fonts.heading_family() == QGuiApplication.font().family()
    assert brand_fonts.body_family() == QGuiApplication.font().family()
