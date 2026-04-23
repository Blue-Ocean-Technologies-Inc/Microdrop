"""Conftest for executor Redis-integration tests.

The broker MUST be configured at module load time, before any test
modules import code that registers @dramatiq.actor decorators —
otherwise those actors register against the default StubBroker and
the RedisBroker we'd swap in via fixture wouldn't see them, producing
an ActorNotFound when the worker tries to dispatch.

Skips the entire module if Redis isn't reachable.
"""

import pytest

from microdrop_utils.broker_server_helpers import (
    configure_dramatiq_broker, is_redis_running,
)


# Configure the broker at module import (before test collection imports
# any actor-registering code). Done unconditionally — if Redis isn't
# reachable the test module will be skipped below anyway, and Dramatiq
# is happy to register actors against an unreachable broker (failures
# only surface on broker.enqueue / worker.start).
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
