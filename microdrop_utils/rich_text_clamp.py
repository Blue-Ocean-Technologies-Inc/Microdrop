# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""Cut rich text to a number of lines, measured with Qt's real text layout
(paragraph spacing and list margins count)."""

# Enthought library imports.
from pyface.qt import QtGui


def clamp_rich_text(html, font, width, lines):
    """``html`` cut to what fits in ``lines`` lines of ``font`` at ``width``,
    measured with the real layout (paragraph spacing and list margins
    count). It ends on a whole line, with an ellipsis when cut; a cut inside
    a list item ends instead after the last whole block (the previous item,
    or the paragraph introducing the list). Returns ``(html, cut)``."""
    document = QtGui.QTextDocument()
    document.setDefaultFont(font)
    document.setDocumentMargin(0)
    document.setHtml(html)
    document.setTextWidth(max(width, 1))

    budget = QtGui.QFontMetricsF(font).lineSpacing() * lines

    if document.size().height() <= budget + 0.5:
        return html, False

    layout = document.documentLayout()
    end = None
    whole_block = True
    block = document.begin()

    while block.isValid():
        top = layout.blockBoundingRect(block).top()
        text_layout = block.layout()
        fitting = [
            text_layout.lineAt(index)
            for index in range(text_layout.lineCount())
            if top + text_layout.lineAt(index).rect().bottom() <= budget + 0.5
        ]

        # The whole block fits: a clean place to stop.
        if len(fitting) == text_layout.lineCount():
            end = block.position() + block.length() - 1
            block = block.next()

            continue

        # Part of a paragraph fits: stop after its last whole line. Part of
        # a list item does not: stop after the last whole block instead.
        if fitting and block.textList() is None:
            last = fitting[-1]
            end = block.position() + last.textStart() + last.textLength()
            whole_block = False

        break

    first = document.begin()

    if end is None:
        end = first.position() + first.layout().lineAt(0).textLength()
        whole_block = False

    # The ellipsis follows the last word, not the space after it.
    while not whole_block and end > 0 and document.characterAt(end - 1).isspace():
        end -= 1

    cursor = QtGui.QTextCursor(document)
    cursor.setPosition(end)
    cursor.movePosition(
        QtGui.QTextCursor.MoveOperation.End, QtGui.QTextCursor.MoveMode.KeepAnchor
    )
    cursor.removeSelectedText()
    cursor.insertText(" …" if whole_block else "…")

    # The ellipsis may not fit on the last line: give up words until it does.
    while document.size().height() > budget + 0.5 and cursor.position() > 2:
        cursor.movePosition(
            QtGui.QTextCursor.MoveOperation.PreviousWord,
            QtGui.QTextCursor.MoveMode.KeepAnchor,
            2,
        )
        cursor.removeSelectedText()

        while (
            cursor.position() > 0
            and document.characterAt(cursor.position() - 1).isspace()
        ):
            cursor.deletePreviousChar()

        cursor.insertText("…")

    return document.toHtml(), True
