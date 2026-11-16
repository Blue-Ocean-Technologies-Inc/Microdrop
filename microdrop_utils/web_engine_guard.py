# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Keep QtWebEngine views out of the process on Linux.

Every Python event filter installed on the QApplication (touch long-press on
the Raspberry Pi, Touch mode, Help mode) makes PySide wrap each event's
receiver as a Python object. A ``QWebEngineView`` renders through
``QtWebEngineCore::RenderWidgetHostViewQtDelegateItem``, a Chromium-side
class built without RTTI, and on Linux PySide's wrapper lookup reads that
class's null type_info — so the first focus or mouse event the view gets
segfaults the whole app (PySide6 6.11.2 through 6.12.0). No Python-side
pre-wrapping avoids it: any attribute access on the wrapper takes the same
path.

Blocking ``PySide6.QtWebEngineWidgets`` turns that crash into an ImportError
every caller already handles: TraitsUI's ``HTMLEditor`` falls back to a
``QTextBrowser``, and the help menu actions render markdown offline or open
pages in the system browser.
"""

# Standard library imports.
import sys

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The module whose views crash; QtWebEngineCore alone creates none.
WEB_ENGINE_WIDGETS_MODULE = "PySide6.QtWebEngineWidgets"


def block_web_engine_views_on_linux():
    """Make importing QtWebEngine widgets raise ImportError on Linux.

    Call before anything imports the module: a view created earlier stays
    exposed to the crash.
    """

    if not sys.platform.startswith("linux"):
        return

    if sys.modules.get(WEB_ENGINE_WIDGETS_MODULE) is not None:
        logger.warning(
            f"{WEB_ENGINE_WIDGETS_MODULE} was imported before it could be "
            f"blocked; web views may crash the app on Linux."
        )

        return

    # A None entry makes the import system raise ModuleNotFoundError.
    sys.modules[WEB_ENGINE_WIDGETS_MODULE] = None
    logger.info(
        f"Blocked {WEB_ENGINE_WIDGETS_MODULE} on Linux; HTML views use the "
        f"text renderer or the system browser."
    )
