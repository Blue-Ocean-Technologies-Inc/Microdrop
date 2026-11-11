# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A read-only rich-text editor for a Str trait that, unlike TraitsUI's
readonly ``QLabel``, shows each fragment's ``title`` as its tooltip.

The widget is a frameless, transparent ``QTextBrowser`` that reads like a
label: it wraps to the width its layout gives it and is exactly as tall
as its content, so the surrounding scrollable view does the scrolling.
``QTextEdit`` already answers a tooltip event with the hovered
fragment's ``QTextCharFormat.toolTip()``, which Qt's HTML importer fills
from ``title``; ``QLabel`` has no such lookup.
"""

# Standard library imports.
import math

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traitsui.api import BasicEditorFactory
from traitsui.qt.editor import Editor


class RichTextBrowser(QtWidgets.QTextBrowser):
    """Read-only rich text sized like a word-wrapped label: its height
    follows its width (height-for-width), it wraps at word boundaries
    only, so its minimum width is the longest word, and it never scrolls
    itself."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.viewport().setAutoFillBackground(False)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(0)
        self.setWordWrapMode(QtGui.QTextOption.WrapMode.WordWrap)

        policy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

        # New text changes the height the layout must give it.
        self.document().documentLayout().documentSizeChanged.connect(
            self.updateGeometry
        )

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        """The content's height when wrapped to ``width``, measured on a
        copy so the shown document's layout is left alone."""
        document = self.document().clone()
        document.setTextWidth(width)

        return math.ceil(document.size().height())

    def sizeHint(self):
        width = super().sizeHint().width()

        return QtCore.QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self):
        # Wrapped to nothing, the ideal width is the longest word.
        document = self.document().clone()
        document.setTextWidth(0)
        width = math.ceil(document.idealWidth())

        return QtCore.QSize(width, self.heightForWidth(width))


class _RichTextEditor(Editor):
    """Shows the trait's value as rich text in a :class:`RichTextBrowser`."""

    def init(self, parent):
        self.control = RichTextBrowser()
        self.update_editor()

    def update_editor(self):
        self.control.setHtml(self.str_value)


class RichTextEditor(BasicEditorFactory):
    """Factory for a read-only rich-text view of a Str trait whose
    fragments show their ``title`` as a tooltip::

        UItem("metadata_text", editor=RichTextEditor(), resizable=True)
    """

    klass = _RichTextEditor
