# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Top-level conftest for dropbot_protocol_controls tests.

Configure the Dramatiq broker to RedisBroker at module-import time,
BEFORE any test module is collected and @dramatiq.actor decorators run.
This ensures actors register against the same broker instance that the
Redis-integration tests (in tests_with_redis_server_need/) will use.

Without this, pytest imports the conftest for the subdirectory AFTER
the parent-directory test modules have already registered their actors
against the old broker, causing ActorNotFound errors in the worker.
"""

from microdrop_utils.broker_server_helpers import configure_dramatiq_broker

configure_dramatiq_broker()
