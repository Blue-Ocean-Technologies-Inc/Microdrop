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

# Third-party imports.
from pydantic import BaseModel, ConfigDict, Field

# Enthought library imports.
from traits.api import HasTraits, Instance, Int, Property, Str

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

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

#: The Tutorial Simulations dock pane: every tutorial's simulations in tabs.
TUTORIAL_SIMULATIONS_DOCK_PANE_ID = f"{PKG}.tutorial_simulations_dock_pane"
TUTORIAL_SIMULATIONS_DOCK_PANE_NAME = "Tutorial Simulations"

#: Shown in the simulations pane until the user picks one, which is what
#: starts its web view.
PICK_SIMULATION_HINT = "Pick a simulation from the list to try it."

#: Run in a loaded tutorial page; defines ``microdropShowSim(demo)``.
SHOW_SIMULATION_SCRIPT_PATH = Path(__file__).parent / "resources" / "show_simulation.js"
MICRODROP_LAUNCHER_README_URL = "https://github.com/Blue-Ocean-Technologies-Inc/microdrop-launcher/blob/main/README.md"

FEEDBACK_URL = "https://blueoceantechnologies.ca/feedback"
GITHUB_ISSUES_URL = "https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues"
SCIBOTS_URL = "https://sci-bots.com"
INFO_EMAIL = "info@sci-bots.com"
SUPPORT_EMAIL = "support@sci-bots.com"

#: The id of the schema addition holding the Help menu's main group, for a
#: contributor's ``SchemaAddition(after=...)``: before/after match an
#: addition's id, not its group's.
HELP_ACTIONS_ADDITION_ID = f"{PKG}.help_actions"

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

    #: Its id for OPEN_TUTORIAL: the page's file name without ``.html``,
    #: e.g. "dropbot_status" (``tutorial_id``).
    id = Property(Str, observe="path")

    def _get_id(self):
        return tutorial_id(self.path) if self.path else ""


def tutorial_id(path):
    """The id OPEN_TUTORIAL names the tutorial page at ``path`` by: its file
    name without the extension, e.g. "dropbot_status" for
    ``.../resources/dropbot_status.html``. A contributor can name its own
    tutorial with ``tutorial_id(ITS_TUTORIAL_HTML_PATH)``."""
    return Path(path).stem


#: The tutorial an unknown id opens instead: the start of the learning path.
GETTING_STARTED_TUTORIAL_ID = tutorial_id(GETTING_STARTED_TUTORIAL_HTML_PATH)

#: Its capacitance calibration chapter (an id in the page), with the clip:
#: where other plugins' "How to calibrate" help links open.
CALIBRATION_TUTORIAL_ANCHOR = "capacitance-calibration"

# ---------------------------------------------------------------------------
# Opening a tutorial from anywhere
# ---------------------------------------------------------------------------
#: Open the tutorial ``tutorial_id`` names, scrolled to the section with the
#: id ``anchor`` if given, as Help > Tutorials opens it. An unknown id opens
#: Getting Started instead. Handled on the frontend by this plugin while it
#: is loaded, which it announces on HELP_AVAILABILITY; e.g. a notification's
#: help link, or a pane's help button.
OPEN_TUTORIAL = "ui/help/open_tutorial"

#: Whether tutorials can be opened now: True when this plugin has started
#: (its OPEN_TUTORIAL listener exists), False when it stops. Help controls
#: elsewhere follow it, disabled until it is True.
HELP_AVAILABILITY = "ui/help/availability"

#: Payload validators build on first use: many plugins import this module.
_DEFERRED_BUILD = ConfigDict(defer_build=True)


class OpenTutorialRequest(BaseModel):
    """Open a tutorial, at a section if given."""

    model_config = _DEFERRED_BUILD

    #: The tutorial's id (``tutorial_id``), e.g. "dropbot_status".
    tutorial_id: str = Field(min_length=1)

    #: The ``id`` of a section in the tutorial's page, e.g. "self-tests";
    #: None opens it at the top.
    anchor: str | None = None


class HelpAvailability(BaseModel):
    """Whether tutorials can be opened (OPEN_TUTORIAL is handled) now."""

    model_config = _DEFERRED_BUILD

    available: bool


open_tutorial_publisher = ValidatedTopicPublisher(
    topic=OPEN_TUTORIAL, validator_class=OpenTutorialRequest
)
help_availability_publisher = ValidatedTopicPublisher(
    topic=HELP_AVAILABILITY, validator_class=HelpAvailability
)

#: This plugin's message listener, which opens the tutorials.
LISTENER_NAME = f"{PKG}_listener"

ACTOR_TOPIC_DICT = {LISTENER_NAME: [OPEN_TUTORIAL]}
