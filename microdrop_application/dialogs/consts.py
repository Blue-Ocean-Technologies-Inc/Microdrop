# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])

# Default WebViewDialog size. Kept here (Qt-free) so callers can reference
# them without importing the dialog module, which pulls in QtWebEngine.
DEFAULT_WEB_VIEW_DIALOG_WIDTH = 1024
DEFAULT_WEB_VIEW_DIALOG_HEIGHT = 768
