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
