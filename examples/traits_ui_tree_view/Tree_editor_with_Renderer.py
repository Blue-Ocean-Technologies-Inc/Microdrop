# (C) Copyright 2004-2023 Enthought, Inc., Austin, TX
# All rights reserved.
#
# This software is provided without warranty under the terms of the BSD
# license included in LICENSE.txt and may be redistributed only under
# the conditions described in the aforementioned license. The license
# is also available online at http://www.enthought.com/licenses/BSD.txt
#
# Thanks for using Enthought open source!

"""
This demo illustrates use of TreeNodeRenderers for displaying more complex
contents inside the cells of a TreeEditor.

To run this demonstration successfully, you must have **NumPy**
(``numpy``) installed.
"""

from random import choice, uniform
import colorsys

import numpy as np

from pyface.qt import qt_api
from pyface.ui_traits import HasBorder
from traits.api import Array, Float, HasTraits, Instance, List, Str, DelegatesTo

from traitsui.api import TreeEditor, TreeNode, UItem, View, RGBColor
from traitsui.qt.helper import wrap_text_with_elision
from traitsui.qt.tree_editor import WordWrapRenderer

from pyface.qt import QtCore, QtGui

from traits.api import Int

from traitsui.tree_node_renderer import AbstractTreeNodeRenderer


class MyDataElement(HasTraits):
    """A node in a tree of data."""

    #: Some text to display.
    text = Str()

    voltage = Str()

    frequency = Str()

    def _voltage_default(self):
        return str(np.random.randint(10000))

    def _frequency_default(self):
        return str(np.random.randint(10000))

    def _cols_default(self):
        return ["The Tree View", "voltage", "frequency"]

    def get_text_for_column_idx(self, column_idx):
        if column_idx-1 == 0:
            return self.voltage
        if column_idx-1 == 1:
            return self.frequency

        else:
            return "NA"


class MyData(HasTraits):
    """The root node for a tree of data."""

    #: The name of the root node.
    name = Str('Protocol Group 1')

    #: The elements contained in the root node.
    elements = List(Instance(MyDataElement))

    cols = DelegatesTo('elements')

    def _elements_default(self):
        DATA_ELEMENTS = (
            'step1',
            'step2',
            'step3',
            'step4',
            'step5 ',
        )
        return [MyDataElement(text=DATA_ELEMENTS[i]) for i in range(5)]


class ColumnTextRenderer(AbstractTreeNodeRenderer):
    """Renderer that draws sparklines into a cell."""

    #: The padding around the text.
    padding = HasBorder(0)

    #: The a good size for the width of the item.
    width_hint = Int(100)

    #: The maximum number of lines to show without eliding.
    max_lines = Int(5)

    #: The extra border applied by Qt internally
    # XXX get this dynamically from Qt? How?
    extra_space = Int(8)

    def paint(self, editor, node, column, object, paint_context):
        """Paint word-wrapped text with elision."""
        painter, option, index = paint_context

        text = self.get_data_text(object, column)

        if editor.factory.show_icons:
            icon_width = option.decorationSize.width() + self.extra_space
            icon_height = option.decorationSize.height()
        else:
            icon_width = 0
            icon_height = 0

        x = option.rect.left() + icon_width + self.padding.left
        y = option.rect.top() + self.padding.top
        width = (
                option.rect.width()
                - icon_width
                - self.padding.left
                - self.padding.right
        )
        height = option.rect.height() - self.padding.top - self.padding.bottom

        lines = wrap_text_with_elision(text, option.font, width, height)

        old_pen = painter.pen()
        if bool(option.state & QtGui.QStyle.StateFlag.State_Selected):
            painter.setPen(QtGui.QPen(option.palette.highlightedText(), 0))
        try:
            rect = painter.drawText(
                x, y, width, height, option.displayAlignment, "\n".join(lines)
            )
        finally:
            painter.setPen(old_pen)

    def size(self, editor, node, column, object, size_context):
        """Return the preferred size for the word-wrapped text

        Parameters
        ----------
        node : ITreeNode instance
            The tree node to render.
        column : int
            The column in the tree that should be rendererd.
        object : object
            The underlying object being edited.
        size_context : object
            A toolkit-dependent context for performing sizing operations.

        Returns
        -------
        size : tuple of (width, height) or None
        """
        option, index = size_context
        font_metrics = QtGui.QFontMetrics(option.font)
        text = self.get_data_text(object, column)
        if editor.factory.show_icons:
            icon_size = option.decorationSize
            icon_width = icon_size.width()
            icon_height = icon_size.height()
        else:
            icon_width = 0
            icon_height = 0

        width = (
                self.width_hint
                - icon_width
                - self.padding.left
                - self.padding.right
        )
        max_height = self.max_lines * font_metrics.lineSpacing()
        lines = wrap_text_with_elision(text, option.font, width, max_height)

        text_height = len(lines) * font_metrics.lineSpacing()

        height = (
                max(icon_height, text_height)
                + self.padding.top
                + self.padding.bottom
                + self.extra_space
        )
        return self.width_hint, height

    def get_data_text(self, object, column):
        return object.get_text_for_column_idx(column)


class ColumnRenderTreeNode(TreeNode):
    """A TreeNode that renders sparklines in column index 1"""

    #: static instance of SparklineRenderer
    #: (it has no state, so this is fine)
    sparkline_renderer = ColumnTextRenderer()

    #: static instance of WordWrapRenderer
    #: (it has no state, so this is fine)
    word_wrap_renderer = WordWrapRenderer()

    def get_renderer(self, object, column=0):
        if column == 0:
            return self.word_wrap_renderer
        else:
            return self.sparkline_renderer



class SparklineTreeView(HasTraits):
    """Class that views the data with sparklines."""

    #: The root of the tree.
    root = Instance(MyData, args=())

    traits_view = View(
        UItem(
            'root',
            editor=TreeEditor(
                nodes=[
                    TreeNode(
                        node_for=[MyData],
                        children='elements',
                        label='name',
                    ),
                    ColumnRenderTreeNode(
                        node_for=[MyDataElement],
                        auto_open=True,
                        label='text',
                    ),
                ],
                column_headers=["Protocol Groups", "voltage", "frequency"],
                hide_root=False,
                editable=False,
            ),
        ),
        resizable=True,
        width=400,
        height=300,
    )



if __name__ == '__main__':
    SparklineTreeView().configure_traits()
