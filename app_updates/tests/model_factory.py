# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Builds updates models for the tests, shared by the fixtures and by tests
that prepare their repository first."""

# Local imports.
from ..model import UpdatesModel
from ..preferences import AppUpdatesPreferences


def make_model(repo_root, preferences):
    """Return a refreshed updates model on ``repo_root``, saving its policy
    to ``preferences``."""
    model = UpdatesModel(
        repo_root=str(repo_root),
        preferences=AppUpdatesPreferences(preferences=preferences),
    )
    model.refresh()

    return model
