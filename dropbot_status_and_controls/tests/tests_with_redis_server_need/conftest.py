# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Leave this partition uncollected when Redis is down: the status pane's
model reads its voltage/frequency bounds from app_globals at class
definition, so without a server its test modules cannot even be imported.
"""

# Microdrop utils imports.
from microdrop_utils.broker_server_helpers import is_redis_running

#: Directory-scoped, unlike a pytest_collection_modifyitems skip hook, which
#: would mark every test in the session.
collect_ignore_glob = [] if is_redis_running() else ["test_*.py"]
