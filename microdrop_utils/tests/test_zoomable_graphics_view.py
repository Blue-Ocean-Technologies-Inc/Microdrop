# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The shared zoom/pan/fit view: zooming in takes over the framing, and pan
mode swaps item interaction for drag-scrolling."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt import QtWidgets

# Microdrop utils imports.
from microdrop_utils.zoomable_graphics_view import ZoomableGraphicsView


@pytest.fixture
def view():
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    return ZoomableGraphicsView(QtWidgets.QGraphicsScene())


def test_zoom_in_stops_auto_fit_and_zoom_out_undoes_it(view):
    view.zoom_in(2)

    assert not view.auto_fit
    assert view.transform().m11() == pytest.approx(2)

    view.zoom_out(2)

    assert view.transform().m11() == pytest.approx(1)


def test_pan_mode_drags_instead_of_interacting(view):
    view.set_pan_mode(True)

    assert view.is_pan_mode()
    assert not view.isInteractive()

    view.set_pan_mode(False)

    assert not view.is_pan_mode()
    assert view.isInteractive()
