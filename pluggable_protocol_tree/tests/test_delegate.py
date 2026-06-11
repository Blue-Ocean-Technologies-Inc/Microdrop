"""Tests for ProtocolItemDelegate — editor lifecycle behaviour.

Regression for the double-paint bug (#396 review): the cell's display
text used to stay painted underneath an open editor, so translucent
editors (the combobox especially) showed both texts overlaid.
"""

from pyface.qt.QtWidgets import QStyleOptionViewItem, QWidget

from pluggable_protocol_tree.builtins.duration_column import (
    make_duration_column,
)
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane


def _pane_with_step(qapp):
    pane = ProtocolTreePane([
        make_type_column(), make_name_column(), make_duration_column(),
    ])
    pane.manager.add_step(values={"name": "visible-name", "duration_s": 2.5})
    return pane


def _index_for(pane, col_id, row=0):
    col = next(i for i, c in enumerate(pane.manager.columns)
               if c.model.col_id == col_id)
    return pane.widget.tree.model().index(row, col)


def test_display_text_suppressed_only_while_editing(qapp):
    pane = _pane_with_step(qapp)
    delegate = pane.widget.delegate
    idx = _index_for(pane, "duration_s")
    other = _index_for(pane, "name")
    parent = QWidget()

    opt = QStyleOptionViewItem()
    delegate.initStyleOption(opt, idx)
    assert opt.text == "2.50"                  # normal display before editing

    editor = delegate.createEditor(parent, None, idx)
    opt = QStyleOptionViewItem()
    delegate.initStyleOption(opt, idx)
    assert opt.text == ""                      # suppressed under the editor

    opt_other = QStyleOptionViewItem()
    delegate.initStyleOption(opt_other, other)
    assert opt_other.text == "visible-name"    # other cells unaffected

    delegate.destroyEditor(editor, idx)
    opt = QStyleOptionViewItem()
    delegate.initStyleOption(opt, idx)
    assert opt.text == "2.50"                  # restored after editing ends


def test_editors_get_opaque_backgrounds(qapp):
    pane = _pane_with_step(qapp)
    delegate = pane.widget.delegate
    parent = QWidget()
    editor = delegate.createEditor(parent, None, _index_for(pane, "duration_s"))
    assert editor.autoFillBackground() is True
    delegate.destroyEditor(editor, _index_for(pane, "duration_s"))
