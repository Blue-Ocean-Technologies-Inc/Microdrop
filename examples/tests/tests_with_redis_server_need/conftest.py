# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import pytest
from ..common import redis_client
from microdrop_utils.broker_server_helpers import start_redis_server, stop_redis_server


@pytest.fixture(autouse=True)
def redis_server_context():
    """
    Context manager for apps that make use of dramatiq.
    Ensures proper startup and shutdown routines.
    """

    proc = start_redis_server()
    client = redis_client()
    client.flushall()  # clear all keys in keys databases in Redis

    yield  # This is where the main logic will execute within the context
    client.flushall()
    # Shutdown routine
    stop_redis_server(proc)