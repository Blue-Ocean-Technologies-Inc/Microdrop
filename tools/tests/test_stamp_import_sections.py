# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pure-logic tests for the import-section-header stamper (issue #613)."""

# Third-party imports.
import pytest

# Microdrop package imports.
from tools.stamp_import_sections import IsortConfig, stamp_source

#: The same section-order / sections config as ruff.toml, duplicated here
#: only as literal test fixture data -- not imported by the script itself.
CONFIG = IsortConfig(
    section_order=[
        "future",
        "standard-library",
        "third-party",
        "enthought",
        "first-party",
        "microdrop-style",
        "microdrop-utils",
        "local-folder",
        "logger",
    ],
    sections={
        "enthought": ["apptools", "envisage", "pyface", "traits", "traitsui"],
        "microdrop-style": ["microdrop_style"],
        "microdrop-utils": ["microdrop_utils"],
        "logger": ["logger"],
    },
)


@pytest.fixture
def repo_root(tmp_path):
    """A scratch tree with just enough first-party packages to classify."""
    (tmp_path / "device_viewer").mkdir()
    (tmp_path / "device_viewer" / "__init__.py").touch()
    (tmp_path / "microdrop_application").mkdir()
    (tmp_path / "microdrop_application" / "__init__.py").touch()
    return tmp_path


def test_all_eight_sections(repo_root):
    source = '''# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Module docstring."""

import math

import shapely

from traits.api import HasTraits

from device_viewer.models.electrodes import Electrodes

from microdrop_style.colors import GREY

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from .consts import PKG

from logger.logger_service import get_logger

logger = get_logger(__name__)
'''
    new_source, changed = stamp_source(source, CONFIG, repo_root)
    assert changed
    expected_block = """\

# Standard library imports.
import math

# Third-party imports.
import shapely

# Enthought library imports.
from traits.api import HasTraits

# Microdrop package imports.
from device_viewer.models.electrodes import Electrodes

# Microdrop style imports.
from microdrop_style.colors import GREY

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from .consts import PKG

# Logger import.
from logger.logger_service import get_logger
"""
    assert expected_block in new_source
    assert new_source.endswith("logger = get_logger(__name__)\n")

    # Idempotent: re-stamping the result is a no-op.
    again, changed_again = stamp_source(new_source, CONFIG, repo_root)
    assert not changed_again
    assert again == new_source


def test_stdlib_and_local_only(repo_root):
    source = """# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import json
from pathlib import Path

from .consts import PKG


def helper():
    return PKG, json, Path
"""
    new_source, changed = stamp_source(source, CONFIG, repo_root)
    assert changed
    assert (
        "# Standard library imports.\nimport json\nfrom pathlib import Path"
        in new_source
    )
    assert "# Local imports.\nfrom .consts import PKG" in new_source
    # No section headers for sections that have no members here.
    assert "# Third-party imports." not in new_source
    assert "# Enthought library imports." not in new_source
    assert "# Logger import." not in new_source

    again, changed_again = stamp_source(new_source, CONFIG, repo_root)
    assert not changed_again


def test_already_stamped_is_noop(repo_root):
    source = """# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import math

# Local imports.
from .consts import PKG


def helper():
    return math, PKG
"""
    new_source, changed = stamp_source(source, CONFIG, repo_root)
    assert not changed
    assert new_source == source


def test_stale_misplaced_headers_are_corrected(repo_root):
    # Wrong label over the stdlib import, and a leftover header for a
    # section that (after reclassification) is empty.
    source = """# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Third-party imports.
import math

# Enthought library imports.
from .consts import PKG


def helper():
    return math, PKG
"""
    new_source, changed = stamp_source(source, CONFIG, repo_root)
    assert changed
    assert "# Standard library imports.\nimport math" in new_source
    assert "# Local imports.\nfrom .consts import PKG" in new_source
    assert "# Third-party imports." not in new_source
    assert "# Enthought library imports." not in new_source

    again, changed_again = stamp_source(new_source, CONFIG, repo_root)
    assert not changed_again


def test_no_imports_is_noop(repo_root):
    source = '''# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A module with no imports at all."""


def helper():
    return 1
'''
    new_source, changed = stamp_source(source, CONFIG, repo_root)
    assert not changed
    assert new_source == source
