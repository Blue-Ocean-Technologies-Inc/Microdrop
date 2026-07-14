"""Switching steps must keep the tree's horizontal scroll position (#516).

With many columns the user often works scrolled right; the running-protocol
highlight and manual step navigation should track the active step
vertically without snapping the view back to the first column.
"""
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.trail_length_column import (
    make_trail_length_column,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.preferences import ProtocolPreferences
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


def _widget_scrolled_right(qapp):
    """A widget narrow enough (and columns wide enough) that the horizontal
    scrollbar has range, scrolled fully right."""
    manager = RowManager(
        columns=[make_name_column(), make_trail_length_column()])
    for i in range(12):
        manager.add_step(values={"name": f"S{i}"})
    widget = ProtocolTreeWidget(manager, preferences=ProtocolPreferences())
    widget.resize(150, 300)
    widget.show()
    header = widget.tree.header()
    header.resizeSection(0, 400)
    header.resizeSection(1, 400)
    qapp.processEvents()
    hbar = widget.tree.horizontalScrollBar()
    assert hbar.maximum() > 0, "test needs a real horizontal scroll range"
    hbar.setValue(hbar.maximum())
    return widget, manager, hbar


def test_set_current_row_keeps_horizontal_scroll(qapp):
    widget, manager, hbar = _widget_scrolled_right(qapp)
    saved = hbar.value()
    widget.set_current_row(manager.get_row((10,)))
    assert hbar.value() == saved
    # Vertical tracking still happened: the current index is the target row.
    assert widget.index_to_path(widget.tree.currentIndex()) == (10,)


def test_highlight_active_row_keeps_horizontal_scroll(qapp):
    widget, manager, hbar = _widget_scrolled_right(qapp)
    saved = hbar.value()
    widget.highlight_active_row(manager.get_row((2,)))
    assert hbar.value() == saved
