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
from traits.api import HasTraits, Instance, Str

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

ARCHITECTURE_HTML_PATH = (
    Path(__file__).parent / "resources" / "microdrop-architecture.html"
)
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


class TutorialEntry(HasTraits):
    """One Help > Tutorials entry: a self-contained, offline HTML page."""

    #: Menu and window title, e.g. "Image Analysis Tutorial".
    title = Str()

    #: The built page (see examples/tutorials/README.md).
    path = Instance(Path)
