# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from traits.api import HasTraits, Instance, Int, Str

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

ARCHITECTURE_HTML_PATH = (
    Path(__file__).parent / "resources" / "microdrop-architecture.html"
)

#: Help > Tutorials page, built from resources/getting_started.src.html.
GETTING_STARTED_TUTORIAL_HTML_PATH = (
    Path(__file__).parent / "resources" / "getting_started.html"
)
GETTING_STARTED_TUTORIAL_TITLE = "Getting Started with MicroDrop"

#: Help > Tutorials page, built from resources/help_logs_storage.src.html.
HELP_LOGS_STORAGE_TUTORIAL_HTML_PATH = (
    Path(__file__).parent / "resources" / "help_logs_storage.html"
)
HELP_LOGS_STORAGE_TUTORIAL_TITLE = "Help, Logs & Saved Files Tutorial"
MICRODROP_LAUNCHER_README_URL = "https://github.com/Blue-Ocean-Technologies-Inc/microdrop-launcher/blob/main/README.md"

FEEDBACK_URL = "https://blueoceantechnologies.ca/feedback"
GITHUB_ISSUES_URL = "https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues"
SCIBOTS_URL = "https://sci-bots.com"
INFO_EMAIL = "info@sci-bots.com"
SUPPORT_EMAIL = "support@sci-bots.com"

# Extension point: Help > Tutorials. Contributions are TutorialEntry records;
# a plugin offers its tutorials with ``List(contributes_to=TUTORIALS)``, and
# the submenu follows plugins loaded or unloaded at runtime. Contributors,
# in this repo or another, import only this module.
TUTORIALS = f"{PKG}.tutorials"

# Help > Tutorials follows a learning path, one section per hundred: start
# here, then the device, protocols, hardware, analysis, managing the app and
# reference pages. A contributor sets ``order=<SECTION> + offset`` to slot an
# entry within its section; the menu sorts by order, then title, and puts a
# separator between sections.
TUTORIAL_SECTION_SPAN = 100
TUTORIAL_ORDER_START = 0
TUTORIAL_ORDER_DEVICE = 100
TUTORIAL_ORDER_PROTOCOLS = 200
TUTORIAL_ORDER_HARDWARE = 300
TUTORIAL_ORDER_ANALYSIS = 400
TUTORIAL_ORDER_MANAGEMENT = 500
TUTORIAL_ORDER_REFERENCE = 600

#: Entries that set no order: a section of their own after every built-in
#: one, alphabetically.
TUTORIAL_ORDER_DEFAULT = 1000


class TutorialEntry(HasTraits):
    """One Help > Tutorials entry: a self-contained, offline HTML page."""

    #: Menu and window title, e.g. "Image Analysis Tutorial".
    title = Str()

    #: The built page (see examples/tutorials/README.md).
    path = Instance(Path)

    #: Place in the menu, lower first: a ``TUTORIAL_ORDER_*`` section plus an
    #: offset. Entries that share an order are sorted by title.
    order = Int(TUTORIAL_ORDER_DEFAULT)
