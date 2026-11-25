# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A small rich-text box for a post's summary, for authors who know no HTML.

Buttons for bold, italic, a bulleted list and adding or removing a link;
what it writes is the feed's own HTML subset, sanitised, so pasting from
Word or a web page keeps the words, bold, italic, lists and links but no
fonts, colours or sizes. TraitsUI has no rich-text editor, hence this Qt
one, which edits a ``summary_html`` trait; while that is empty it shows the
plain ``summary`` named by ``plain_name``.
"""

# Standard library imports.
from html import escape

# Enthought library imports.
from pyface.qt import QtGui, QtWidgets
from traits.api import Any, Bool, Str
from traitsui.api import BasicEditorFactory
from traitsui.qt.editor import Editor

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import warning

# Local imports.
from ..models.feed_schema import is_web_url
from ..services.feed_html import sanitise_summary_html

#: The toolbar: button text, tooltip and the editor method it runs.
TOOL_BUTTONS = (
    ("B", "Bold: select words, then click", "_toggle_bold"),
    ("I", "Italic: select words, then click", "_toggle_italic"),
    (
        "• List",
        "Bulleted list: make the current lines a list, or undo it",
        "_toggle_list",
    ),
    ("Link…", "Add a link: select words, then give the web address", "_add_link"),
    ("Unlink", "Remove the link from the selected words", "_remove_link"),
)

#: Ordered list styles, written <ol>; any other list is <ul>.
_ORDERED_STYLES = (
    QtGui.QTextListFormat.Style.ListDecimal,
    QtGui.QTextListFormat.Style.ListLowerAlpha,
    QtGui.QTextListFormat.Style.ListUpperAlpha,
    QtGui.QTextListFormat.Style.ListLowerRoman,
    QtGui.QTextListFormat.Style.ListUpperRoman,
)

_BOLD = QtGui.QFont.Weight.Bold.value


def _fragment_html(fragment):
    """One run of same-formatted text as HTML."""
    text = escape(fragment.text(), quote=False).replace(" ", "<br>")
    text_format = fragment.charFormat()

    if text_format.fontWeight() >= _BOLD:
        text = f"<b>{text}</b>"

    if text_format.fontItalic():
        text = f"<i>{text}</i>"

    if text_format.isAnchor() and text_format.anchorHref():
        text = f'<a href="{escape(text_format.anchorHref())}">{text}</a>'

    return text


def _block_html(block):
    parts = []
    fragments = block.begin()

    while not fragments.atEnd():
        fragment = fragments.fragment()

        if fragment.isValid():
            parts.append(_fragment_html(fragment))

        fragments += 1

    return "".join(parts)


def document_to_summary_html(document):
    """A QTextDocument as the feed's HTML subset: paragraphs and lists of
    bold, italic and linked text, sanitised."""
    parts = []
    open_list = None
    block = document.begin()

    while block.isValid():
        text_list = block.textList()
        inner = _block_html(block)

        if text_list is None:
            if open_list is not None:
                parts.append(f"</{open_list[1]}>")
                open_list = None

            if inner.strip():
                parts.append(f"<p>{inner}</p>")

        else:
            ordered = text_list.format().style() in _ORDERED_STYLES
            tag = "ol" if ordered else "ul"

            if open_list is None or open_list[0] != text_list.objectIndex():
                if open_list is not None:
                    parts.append(f"</{open_list[1]}>")

                parts.append(f"<{tag}>")
                open_list = (text_list.objectIndex(), tag)

            parts.append(f"<li>{inner}</li>")

        block = block.next()

    if open_list is not None:
        parts.append(f"</{open_list[1]}>")

    return sanitise_summary_html("".join(parts))


class _CleanPasteTextEdit(QtWidgets.QTextEdit):
    """Pastes rich text sanitised, so it keeps no fonts, colours or sizes."""

    def insertFromMimeData(self, source):
        if source.hasHtml():
            self.textCursor().insertHtml(sanitise_summary_html(source.html()))

        elif source.hasText():
            self.textCursor().insertText(source.text())


class _RichTextEditor(Editor):
    """Edits a sanitised HTML trait in a QTextEdit with a formatting bar."""

    #: The text box.
    _text_edit = Any()

    #: Whether the value is being written from the text box.
    _writing = Bool(False)

    def init(self, parent):
        self.control = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.control)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(2)

        for text, tooltip, method in TOOL_BUTTONS:
            button = QtWidgets.QToolButton(self.control)
            button.setText(text)
            button.setToolTip(tooltip)
            button.clicked.connect(getattr(self, method))
            bar.addWidget(button)

        bar.addStretch()
        layout.addLayout(bar)

        self._text_edit = _CleanPasteTextEdit(self.control)
        self._text_edit.setAcceptRichText(True)
        self._text_edit.setPlaceholderText(
            "A few sentences for the card. Select words to make them bold, "
            "italic or a link."
        )
        self._text_edit.setMinimumHeight(110)
        self._text_edit.textChanged.connect(self._write_value)
        layout.addWidget(self._text_edit)

    def update_editor(self):
        if self._writing:
            return

        plain = getattr(self.object, self.factory.plain_name, "")

        self._text_edit.blockSignals(True)

        if self.value:
            self._text_edit.setHtml(self.value)

        else:
            self._text_edit.setPlainText(plain)

        self._text_edit.blockSignals(False)

    def dispose(self):
        if self._text_edit is not None:
            self._text_edit.textChanged.disconnect(self._write_value)

        super().dispose()

    def _write_value(self):
        self._writing = True

        try:
            self.value = document_to_summary_html(self._text_edit.document())

        finally:
            self._writing = False

    # ------------------------------------------------------------------ #
    # Toolbar                                                             #
    # ------------------------------------------------------------------ #

    def _toggle_bold(self):
        weight = QtGui.QFont.Weight
        bold = self._text_edit.fontWeight() >= _BOLD
        self._text_edit.setFontWeight(weight.Normal if bold else weight.Bold)

    def _toggle_italic(self):
        self._text_edit.setFontItalic(not self._text_edit.fontItalic())

    def _toggle_list(self):
        cursor = self._text_edit.textCursor()
        text_list = cursor.currentList()

        if text_list is None:
            cursor.createList(QtGui.QTextListFormat.Style.ListDisc)

            return

        text_list.remove(cursor.block())
        block_format = cursor.blockFormat()
        block_format.setIndent(0)
        cursor.setBlockFormat(block_format)

    def _add_link(self):
        cursor = self._text_edit.textCursor()

        if not cursor.hasSelection():
            warning(
                self.control,
                "Select the words to turn into a link first.",
                title="Add link",
                cancel=False,
            )

            return

        url, accepted = QtWidgets.QInputDialog.getText(
            self.control, "Add link", "Web address the words link to (https://…):"
        )
        url = url.strip()

        if not accepted or not url:
            return

        if not is_web_url(url):
            warning(
                self.control,
                f"“{url}” is not a web address. Links must start with https://.",
                title="Add link",
                cancel=False,
            )

            return

        link_format = QtGui.QTextCharFormat()
        link_format.setAnchor(True)
        link_format.setAnchorHref(url)
        link_format.setFontUnderline(True)
        link_format.setForeground(self._text_edit.palette().link())
        cursor.mergeCharFormat(link_format)

    def _remove_link(self):
        cursor = self._text_edit.textCursor()

        if not cursor.hasSelection():
            cursor.select(QtGui.QTextCursor.SelectionType.WordUnderCursor)

        plain_format = cursor.charFormat()
        plain_format.setAnchor(False)
        plain_format.setAnchorHref("")
        plain_format.setFontUnderline(False)
        plain_format.clearForeground()
        cursor.setCharFormat(plain_format)


class RichTextEditor(BasicEditorFactory):
    """Edit sanitised summary HTML with bold, italic, list and link buttons."""

    klass = _RichTextEditor

    #: The plain-text trait shown while the HTML one is empty.
    plain_name = Str("summary")
