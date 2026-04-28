"""Conftest for peripheral_protocol_controls Redis-integration tests.

The broker MUST be configured at module load time, before any test
modules import code that registers @dramatiq.actor decorators —
otherwise those actors register against the default StubBroker and
the RedisBroker we'd swap in via fixture wouldn't see them, producing
an ActorNotFound when the worker tries to dispatch.

NOTE: The parent tests/conftest.py already calls configure_dramatiq_broker()
so that all actor imports in non-Redis tests also land on the RedisBroker.
We do NOT call it again here — a second call creates a new broker instance
and wipes previously-registered actors.

Skips the entire module if Redis isn't reachable.

Mirrors dropbot_protocol_controls/tests/tests_with_redis_server_need/conftest.py
from PPT-4.
"""

import dramatiq
import pytest

from microdrop_utils.broker_server_helpers import (
    configure_dramatiq_broker, is_redis_running,
)
from dramatiq.brokers.redis import RedisBroker


# Only configure if not already on a RedisBroker — the parent conftest.py
# should have done it first, but guard here for correctness when this
# directory is targeted directly (e.g. pytest tests_with_redis_server_need/).
if not isinstance(dramatiq.get_broker(), RedisBroker):
    configure_dramatiq_broker()


def pytest_collection_modifyitems(config, items):
    if is_redis_running():
        return
    skip_marker = pytest.mark.skip(reason="Redis broker not reachable")
    for item in items:
        item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def router_actor():
    """One MessageRouterActor for the whole pytest session.

    DramatiqControllerBase.traits_init registers the underlying actor
    on construction, and Dramatiq raises ValueError on duplicate actor
    names — so each test that calls MessageRouterActor() works in
    isolation but two tests in the same session conflict. Construct
    once, reuse everywhere.
    """
    from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterActor
    return MessageRouterActor()
