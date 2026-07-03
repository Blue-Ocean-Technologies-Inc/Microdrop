# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

#: Extension-point id: QWidget instances to show in the app status bar.
STATUS_BAR_ICONS = "status_bar_icons"

#: Uniform gap (px) between adjacent contributed status-bar icons.
ICON_SPACING = 10

#: Status-bar message shown from startup until something replaces it.
DEFAULT_STATUS_MESSAGE = "Free Mode"

#: Contents margins (left, top, right, bottom) of the status bar.
STATUS_BAR_CONTENTS_MARGINS = (30, 0, 30, 0)
