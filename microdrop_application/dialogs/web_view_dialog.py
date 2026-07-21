"""Generic dialog rendering an HTML page in an embedded web view.

Import this module lazily (e.g. inside an ``Action.perform``) so QtWebEngine
is only initialized when a dialog is first opened; it is deliberately not
re-exported from the ``dialogs`` package ``__init__`` for the same reason.
"""

import webbrowser
from pathlib import Path

from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from pyface.qt.QtWidgets import QDialog, QVBoxLayout
from pyface.qt.QtCore import QUrl

from .consts import DEFAULT_WEB_VIEW_DIALOG_WIDTH, DEFAULT_WEB_VIEW_DIALOG_HEIGHT


class ExternalLinkWebEnginePage(QWebEnginePage):
    """Web page that opens every clicked link in the system browser.

    Keeps the dialog's content fixed while letting the default browser
    handle navigation — including file downloads, which QWebEngineView
    would otherwise silently ignore.
    """

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if navigation_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            webbrowser.open(url.toString())
            return False
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)


class WebViewDialog(QDialog):
    """Dialog whose whole content area is a web view.

    ``source`` is either a URL string (remote page, e.g. a GitHub-rendered
    README) or a ``pathlib.Path`` to a local HTML file. Alternatively pass
    ``html_content`` (a full HTML document string) to render it directly.
    With ``open_links_externally`` the content stays fixed and clicked links
    open in the system browser instead of navigating the dialog.
    """

    def __init__(self, source=None, title="",
                 width=DEFAULT_WEB_VIEW_DIALOG_WIDTH,
                 height=DEFAULT_WEB_VIEW_DIALOG_HEIGHT,
                 html_content=None,
                 open_links_externally=False,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(width, height)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web_view = QWebEngineView()
        if open_links_externally:
            self.web_view.setPage(ExternalLinkWebEnginePage(self.web_view))
        if html_content is not None:
            self.web_view.setHtml(html_content)
        else:
            url = QUrl.fromLocalFile(str(source)) if isinstance(source, Path) else QUrl(source)
            self.web_view.load(url)
        layout.addWidget(self.web_view)
