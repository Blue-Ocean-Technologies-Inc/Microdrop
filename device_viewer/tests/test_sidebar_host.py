# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the device viewer sidebar host and its SidebarSection unit."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtWidgets import QApplication, QLabel

# Microdrop package imports.
from device_viewer.views.sidebar.host import build_reveal_button, build_sidebar
from device_viewer.views.sidebar.section import SidebarSection, stack_widgets

# Microdrop utils imports.
from microdrop_utils.pyside_helpers import CollapsibleVStackBox


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _stub_section(title, collapsed=False):
    """A section as a builder would return it, with a placeholder widget."""
    return SidebarSection(title=title, widget=QLabel(title), collapsed=collapsed)


def _boxes(scroll_area):
    """The collapsible boxes in the sidebar, top to bottom."""
    layout = scroll_area.widget().layout()

    return [
        layout.itemAt(index).widget()
        for index in range(layout.count())
        if isinstance(layout.itemAt(index).widget(), CollapsibleVStackBox)
    ]


def test_sections_are_stacked_in_order_with_their_titles():
    titles = ["Viewport Controls", "Camera Controls", "Paths", "Zones"]

    scroll_area = build_sidebar([_stub_section(title) for title in titles])

    assert [box.toggle_button.text() for box in _boxes(scroll_area)] == titles


def test_collapsed_flag_sets_the_initial_expansion():
    scroll_area = build_sidebar(
        [_stub_section("Open"), _stub_section("Shut", collapsed=True)]
    )

    open_box, shut_box = _boxes(scroll_area)

    assert open_box.is_expanded()
    assert not shut_box.is_expanded()
    assert shut_box.content_container.isHidden()


def test_each_box_holds_its_sections_widget():
    section = _stub_section("Calibration")

    (box,) = _boxes(build_sidebar([section]))

    assert box.content_widgets == [section.widget]


def test_none_sections_are_skipped():
    scroll_area = build_sidebar([None, _stub_section("Zones"), None])

    assert [box.toggle_button.text() for box in _boxes(scroll_area)] == ["Zones"]


def test_sections_are_followed_by_a_stretch():
    scroll_area = build_sidebar([_stub_section("Zones")])
    layout = scroll_area.widget().layout()

    assert layout.itemAt(layout.count() - 1).spacerItem() is not None


def test_stack_widgets_keeps_order_without_margins_or_spacing():
    labels = [QLabel("a"), QLabel("b"), QLabel("c")]

    container = stack_widgets(labels)
    layout = container.layout()

    assert [layout.itemAt(index).widget() for index in range(3)] == labels
    assert layout.spacing() == 0
    assert layout.contentsMargins().left() == 0


def test_reveal_button_toggles_the_sidebar():
    scroll_area = build_sidebar([_stub_section("Zones")])
    reveal_button = build_reveal_button(scroll_area)

    reveal_button.click()

    assert scroll_area.isHidden()
    assert reveal_button.text() == "chevron_left"

    reveal_button.click()

    assert not scroll_area.isHidden()
    assert reveal_button.text() == "chevron_right"
