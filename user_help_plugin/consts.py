# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from pathlib import Path

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

ARCHITECTURE_HTML_PATH = Path(__file__).parent / "resources" / "microdrop-architecture.html"
MICRODROP_LAUNCHER_README_URL = "https://github.com/Blue-Ocean-Technologies-Inc/microdrop-launcher/blob/main/README.md"

FEEDBACK_URL = "https://blueoceantechnologies.ca/feedback"
GITHUB_ISSUES_URL = "https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues"
SCIBOTS_URL = "https://sci-bots.com"
INFO_EMAIL = "info@sci-bots.com"
SUPPORT_EMAIL = "support@sci-bots.com"