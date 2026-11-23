# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""TraitsUI editor rendering a Markdown ``Str`` trait in a read-only
``QTextBrowser`` — no WebEngine, so it works where ``HTMLEditor`` cannot
(QtWebEngineWidgets is blocked on the Pi)."""

# Enthought library imports.
from pyface.qt import QtWidgets
from traits.api import Int
from traitsui.api import BasicEditorFactory
from traitsui.qt.editor import Editor as QtEditor

# Microdrop utils imports.
from microdrop_utils.markdown_helpers import escape_tag_like_tokens

#: A reader this close to the bottom (px) is following the newest text.
FOLLOW_TOLERANCE_PX = 4


class _MarkdownBrowserEditor(QtEditor):
    """The Qt half: re-renders on every change, keeping the reader's scroll
    position unless they were at the bottom (then it follows new text)."""

    def init(self, parent):
        self.control = QtWidgets.QTextBrowser()
        self.control.setReadOnly(True)
        self.control.setOpenExternalLinks(False)
        self.control.setMinimumHeight(self.factory.min_height)

        self.update_editor()

    def update_editor(self):
        """Render the trait's Markdown."""
        bar = self.control.verticalScrollBar()
        position = bar.value()
        following = position >= bar.maximum() - FOLLOW_TOLERANCE_PX

        # QTextDocument reads any <token> as inline HTML and drops the rest.
        self.control.setMarkdown(escape_tag_like_tokens(self.value or ""))

        bar.setValue(bar.maximum() if following else position)


class MarkdownBrowserEditor(BasicEditorFactory):
    """Show a Markdown ``Str`` trait, rendered (headings, bold, tables)."""

    klass = _MarkdownBrowserEditor

    #: Minimum height (px); the browser scrolls its own content.
    min_height = Int(200)
