# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Session-wide test setup.

Load pydantic completely before any test module can import Qt. PySide6's
import hook inspects each imported module once; inspecting pydantic.errors
runs pydantic's lazy module ``__getattr__``, which raises ImportError while
pydantic._internal._validators is still initialising. So a test module that
loads only pydantic.BaseModel before the first Qt import, followed by one
that first imports pydantic.Field after it, fails at collection. The app
entry points import Qt before pydantic, so they never hit this order.
"""

# Third-party imports.
import pydantic.fields  # noqa: F401
