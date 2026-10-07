# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Shared kit for MicroDrop's in-app HTML tutorials.

``tutorial.css`` and ``tutorial.js`` are inlined into every built tutorial by
``examples/tutorials/build_tutorial.py``; ``glyphs`` traces the app's toolbar
icons into SVG so a tutorial can show the real buttons. See
``examples/tutorials/README.md`` for the authoring format.
"""

# Standard library imports.
from pathlib import Path

TUTORIAL_KIT_DIR = Path(__file__).parent
TUTORIAL_CSS_PATH = TUTORIAL_KIT_DIR / "tutorial.css"
TUTORIAL_JS_PATH = TUTORIAL_KIT_DIR / "tutorial.js"
