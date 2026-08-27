# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Message schema for the SELF_TESTS_PROGRESS topic.

The dropbot controller owns the topic; the frontend task and the mock
controller import these as the pub/sub payload contract (sanctioned
cross-plugin message-schema import).
"""

import json


class TestEvent:
    SESSION_START = "SESSION_START"
    PROGRESS = "PROGRESS"
    SESSION_END = "SESSION_END"
    ERROR = "ERROR"


def create_test_progress_message(event_type, **kwargs):
    """Helper to ensure consistent message structure"""
    return json.dumps({"type": event_type, "payload": kwargs})
