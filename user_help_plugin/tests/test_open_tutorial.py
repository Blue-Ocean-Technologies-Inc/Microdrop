# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Opening a tutorial by id: its id, the request's payload, and the page
source with a section anchor."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
import pytest
from pydantic import ValidationError

# Microdrop package imports.
from user_help_plugin.consts import (
    HelpAvailability,
    OpenTutorialRequest,
    TutorialEntry,
    tutorial_id,
)
from user_help_plugin.menus import tutorial_source

PAGE = Path(__file__).resolve().parent / "dropbot_status.html"


def test_a_tutorial_is_named_by_its_page():
    assert tutorial_id(PAGE) == "dropbot_status"
    assert TutorialEntry(title="Dropbot Status", path=PAGE).id == "dropbot_status"


def test_a_request_needs_an_id_and_may_name_a_section():
    request = OpenTutorialRequest.model_validate_json(
        '{"tutorial_id": "dropbot_status", "anchor": "part-tools"}'
    )

    assert (request.tutorial_id, request.anchor) == ("dropbot_status", "part-tools")
    assert OpenTutorialRequest(tutorial_id="zones").anchor is None

    with pytest.raises(ValidationError):
        OpenTutorialRequest(tutorial_id="")


def test_availability_is_a_flag():
    assert HelpAvailability.model_validate_json('{"available": true}').available


def test_a_section_is_the_page_url_with_its_anchor():
    assert tutorial_source(PAGE) == PAGE
    assert tutorial_source(PAGE, "connection") == f"{PAGE.as_uri()}#connection"
