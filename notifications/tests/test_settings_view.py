# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The settings window, built as the plugin builds it (``edit_traits`` with
the real view): its "By kind" tab, closing it and opening it again. Run
headless with ``QT_QPA_PLATFORM=offscreen``."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from traits.api import pop_exception_handler, push_exception_handler

# Microdrop package imports.
from notifications.consts import NotificationCategorySpec
from notifications.models.settings import NotificationSettings
from notifications.models.settings_window import SettingsWindowState
from notifications.views.settings_kinds import KindsPanel
from notifications.views.settings_view import group_settings_view, settings_view

SPECS = [
    NotificationCategorySpec(id="demo.done", group="Demo", label="Done"),
    NotificationCategorySpec(id="demo.failed", group="Demo", label="Failed"),
    NotificationCategorySpec(id="other.lost", group="Other", label="Lost"),
]


@pytest.fixture(autouse=True)
def qapp():
    push_exception_handler(reraise_exceptions=True)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    yield app

    pop_exception_handler()


@pytest.fixture
def settings():
    settings = NotificationSettings()
    settings.declare(SPECS)

    return settings


def _flush():
    """Run queued timers and the deletions TraitsUI deferred."""
    QtWidgets.QApplication.processEvents()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    QtWidgets.QApplication.processEvents()


def _open(settings, window):
    view, context = settings_view(settings, window)
    ui = settings.edit_traits(view=view, context=context)
    tabs = ui.control.findChild(QtWidgets.QTabWidget)

    tabs.setCurrentIndex(tabs.count() - 1)
    _flush()

    assert tabs.tabText(tabs.currentIndex()) == "By kind"

    return ui, ui.control.findChild(KindsPanel)


def test_by_kind_tab_builds_a_section_per_group(settings):
    ui, panel = _open(settings, SettingsWindowState())

    assert [section.group.name for section in panel.sections] == ["Demo", "Other"]

    done = panel.sections[0].rows[0]
    done.popup.click()

    assert not done.category.popup

    ui.dispose()
    _flush()


def test_closing_lets_the_settings_go_and_reopening_works(settings):
    window = SettingsWindowState()
    ui, panel = _open(settings, window)
    binding = panel._binding

    # A kind declared just before the window closes queues a rebuild.
    settings.declare(
        [NotificationCategorySpec(id="late.one", group="Late", label="One")]
    )
    ui.dispose()

    assert binding.settings is None

    _flush()

    ui, panel = _open(settings, window)

    assert [section.group.name for section in panel.sections] == [
        "Demo",
        "Other",
        "Late",
    ]

    ui.dispose()
    _flush()


def test_one_owners_page_lists_only_its_kinds(settings):
    view, context = group_settings_view(settings, "Other")
    ui = settings.edit_traits(view=view, context=context)
    panel = ui.control.findChild(KindsPanel)

    assert [section.group.name for section in panel.sections] == ["Other"]

    ui.dispose()
    _flush()
