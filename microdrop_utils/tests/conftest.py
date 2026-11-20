# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Fixtures shared by the microdrop_utils tests. The git repository fixtures
are imported here for pytest to register; no test module imports them."""

# Microdrop utils imports.
from microdrop_utils.tests.git_repo_fixtures import (  # noqa: F401
    clone,
    clone_at_v1_2,
    source_repo,
)
