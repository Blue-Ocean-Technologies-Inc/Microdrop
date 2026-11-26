# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""What the header's Collapse or Expand all toggle offers, for the
sections' states."""

# Standard library imports.
from types import SimpleNamespace

# Microdrop package imports.
from notifications.consts import NotificationSection
from notifications.models.notifications_pane_model import (
    COLLAPSE_ALL,
    EXPAND_ALL,
    fold_all_toggle,
)


def test_any_expanded_section_offers_collapse_all():
    sections = [
        NotificationSection(id="news", expanded=True),
        NotificationSection(id="plugins", expanded=False),
    ]

    assert fold_all_toggle(sections) == COLLAPSE_ALL


def test_all_collapsed_offers_expand_all():
    sections = [
        NotificationSection(id="news", expanded=False),
        NotificationSection(id="plugins", expanded=False),
    ]

    assert fold_all_toggle(sections) == EXPAND_ALL


def test_a_hidden_expanded_section_does_not_count():
    # Needs attention while empty: expanded, but not shown.
    hidden = SimpleNamespace(expanded=True, available=False)
    sections = [hidden, NotificationSection(id="news", expanded=False)]

    assert fold_all_toggle(sections) == EXPAND_ALL


def test_no_sections_offers_expand_all():
    assert fold_all_toggle([]) == EXPAND_ALL
