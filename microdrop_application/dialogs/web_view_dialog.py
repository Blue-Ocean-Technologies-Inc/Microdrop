"""Generic dialog rendering an HTML page in an embedded web view.

Import this module lazily (e.g. inside an ``Action.perform``) so QtWebEngine
is only initialized when a dialog is first opened; it is deliberately not
re-exported from the ``dialogs`` package ``__init__`` for the same reason.
"""

from pathlib import Path

from PySide6.QtWebEngineWidgets import QWebEngineView
from pyface.qt.QtWidgets import QDialog, QVBoxLayout
from pyface.qt.QtCore import QUrl

from .consts import DEFAULT_WEB_VIEW_DIALOG_WIDTH, DEFAULT_WEB_VIEW_DIALOG_HEIGHT


class WebViewDialog(QDialog):
    """Dialog whose whole content area is a web view.

    ``source`` is either a URL string (remote page, e.g. a GitHub-rendered
    README) or a ``pathlib.Path`` to a local HTML file. Alternatively pass
    ``html_content`` (a full HTML document string) to render it directly.
    """

    def __init__(self, source=None, title="",
                 width=DEFAULT_WEB_VIEW_DIALOG_WIDTH,
                 height=DEFAULT_WEB_VIEW_DIALOG_HEIGHT,
                 html_content=None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(width, height)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web_view = QWebEngineView()
        if html_content is not None:
            self.web_view.setHtml(html_content)
        else:
            url = QUrl.fromLocalFile(str(source)) if isinstance(source, Path) else QUrl(source)
            self.web_view.load(url)
        layout.addWidget(self.web_view)
