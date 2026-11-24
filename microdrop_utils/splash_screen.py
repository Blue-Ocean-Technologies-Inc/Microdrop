# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""MicroDrop's startup splash screen.

It lives here rather than in ``microdrop_application`` because the launcher
opens it right after the source update step, before any plugin package is
imported. Importing this module initialises the pyface toolkit, which
creates the QApplication.
"""

# Standard library imports.
import time
from pathlib import Path

# Enthought library imports.
from pyface.image_resource import ImageResource
from pyface.qt import QtCore, QtWidgets
from pyface.splash_screen import SplashScreen
from pyface.ui_traits import Image
from traits.api import Str

#: The splash artwork, as a path so no ``microdrop_style`` module is imported.
SPLASH_IMAGE_PATH = (
    Path(__file__).resolve().parent.parent
    / "microdrop_style"
    / "icons"
    / "Microdrop_Primary_Logo_FHD.png"
)

#: Text shown on the splash until log messages replace it.
SPLASH_TEXT = "Microdrop-Next-Gen v.beta"

#: Largest share of the available screen the splash may cover.
MAX_SCREEN_FRACTION = 0.6

#: Longest wait for the window system to expose a freshly shown splash.
EXPOSE_TIMEOUT_S = 1.0


class _PromptQSplashScreen(QtWidgets.QSplashScreen):
    """QSplashScreen whose show() returns at once instead of stalling ~1 s.

    ``QSplashScreen::event`` answers the widget's Show event by waiting up
    to 1 s for the native window to be exposed, but Qt only shows the native
    window after that event returns, so the wait always runs to its timeout.
    ``MicrodropSplashScreen.open`` waits for the exposure afterwards instead.
    """

    def event(self, event):
        if event.type() == QtCore.QEvent.Type.Show:
            return QtWidgets.QWidget.event(self, event)

        return super().event(event)


class MicrodropSplashScreen(SplashScreen):
    """The MicroDrop splash: top-most, sized to the screen, painted on open.

    ``open`` leaves an already-open splash alone, so the launcher can open it
    before the application exists and hand it over as the application's
    ``splash_screen``, which the pyface GUI opens again.
    """

    #: The MicroDrop logo artwork.
    image = Image(ImageResource(str(SPLASH_IMAGE_PATH)))

    #: The release banner.
    text = Str(SPLASH_TEXT)

    def open(self):
        """Open the splash and paint it before returning."""
        if self.control is not None:
            return True

        opened = super().open()

        if opened:
            self._paint_when_exposed()

        return opened

    def _create_control(self, parent):
        """Create the splash, capped to the screen and kept on top.

        A bare ``QSplashScreen`` is frameless and top-level but does not carry
        ``WindowStaysOnTopHint``, so while the app boots it can get buried
        behind the task window.
        """
        control = _PromptQSplashScreen(self.image.create_image())
        self._qt4_show_message(control)

        # The FHD artwork (1920x1080) overflows small screens (the portable
        # device is 1280x800) and, being always on top, locks the user out
        # of everything under it — cap it and re-centre.
        available = control.screen().availableGeometry()
        target = available.size() * MAX_SCREEN_FRACTION
        pixmap = control.pixmap()

        if pixmap.width() > target.width() or pixmap.height() > target.height():
            control.setPixmap(
                pixmap.scaled(
                    target,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            )
            control.move(available.center() - control.rect().center())

        control.setWindowFlags(
            control.windowFlags() | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        control.raise_()
        control.activateWindow()

        return control

    def _paint_when_exposed(self):
        """Process events until the splash is exposed, then paint it.

        Startup keeps the GUI thread busy until the event loop starts, so the
        splash has to be on screen before ``open`` returns.
        """
        window = self.control.windowHandle()
        deadline = time.monotonic() + EXPOSE_TIMEOUT_S

        while (
            window is not None
            and not window.isExposed()
            and time.monotonic() < deadline
        ):
            QtCore.QCoreApplication.processEvents()

        self.control.repaint()
