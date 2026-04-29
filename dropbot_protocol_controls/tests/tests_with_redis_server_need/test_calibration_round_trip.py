"""End-to-end Redis-backed test: a real CALIBRATION_DATA publish flows
through the router and the calibration_data_listener actor into the
process-wide CalibrationCache singleton, and `cache_changed` fires.

Requires a running Redis server on localhost:6379. The conftest skips
the whole module if Redis is unreachable.
"""
import json
import time
from threading import Event as PyEvent

import dramatiq
import pytest

# Strip Prometheus middleware before anything else touches the broker —
# mirrors the PPT-4 round-trip test's preamble.
from microdrop_utils.broker_server_helpers import remove_middleware_from_dramatiq_broker
remove_middleware_from_dramatiq_broker(
    middleware_name="dramatiq.middleware.prometheus",
    broker=dramatiq.get_broker(),
)

from device_viewer.consts import CALIBRATION_DATA
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from dropbot_protocol_controls.consts import CALIBRATION_LISTENER_ACTOR_NAME
# Importing the module registers the @dramatiq.actor decorator — must
# happen after the broker is the RedisBroker (parent conftest configures
# this at collection start) so the actor lands on the right broker.
from dropbot_protocol_controls.services.calibration_cache import cache
from dropbot_protocol_controls.services import calibration_cache as _calibration_module  # noqa: F401


@pytest.fixture(autouse=True)
def _reset_cache():
    cache.trait_set(
        liquid_capacitance_over_area=0.0,
        filler_capacitance_over_area=0.0,
    )
    yield
    cache.trait_set(
        liquid_capacitance_over_area=0.0,
        filler_capacitance_over_area=0.0,
    )


@pytest.fixture
def calibration_subscription(router_actor):
    """Wire the listener subscription that MessageRouterPlugin.start()
    would build from ACTOR_TOPIC_DICT in production. Workers come up
    here too so the broker is draining by the time the test publishes.
    """
    from dramatiq import Worker

    broker = dramatiq.get_broker()
    broker.flush_all()

    router_actor.message_router_data.add_subscriber_to_topic(
        topic=CALIBRATION_DATA,
        subscribing_actor_name=CALIBRATION_LISTENER_ACTOR_NAME,
    )

    worker = Worker(broker, worker_timeout=100)
    worker.start()
    try:
        yield router_actor
    finally:
        worker.stop()
        router_actor.message_router_data.remove_subscriber_from_topic(
            topic=CALIBRATION_DATA,
            subscribing_actor_name=CALIBRATION_LISTENER_ACTOR_NAME,
        )


def test_calibration_publish_updates_cache_and_fires_event(calibration_subscription):
    cache_changed_spy = PyEvent()

    def _handler(event):
        cache_changed_spy.set()

    cache.observe(_handler, "cache_changed")
    try:
        publish_message(
            topic=CALIBRATION_DATA,
            message=json.dumps({
                "liquid_capacitance_over_area": 2.0,
                "filler_capacitance_over_area": 0.5,
            }),
        )

        # Round-trip through Redis + worker dispatch is async; poll
        # until the cache reflects the new values or the deadline lapses.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if cache.liquid_capacitance_over_area == 2.0:
                break
            time.sleep(0.05)

        assert cache.liquid_capacitance_over_area == pytest.approx(2.0)
        assert cache.filler_capacitance_over_area == pytest.approx(0.5)
        assert cache.capacitance_per_unit_area() == pytest.approx(1.5)

        assert cache_changed_spy.wait(timeout=5.0), (
            "cache_changed did not fire within 5s of cache update"
        )
    finally:
        cache.observe(_handler, "cache_changed", remove=True)


def test_malformed_calibration_payload_does_not_update_cache(calibration_subscription):
    cache_changed_spy = PyEvent()

    def _handler(event):
        cache_changed_spy.set()

    cache.observe(_handler, "cache_changed")
    try:
        publish_message(
            topic=CALIBRATION_DATA,
            message="not-json",
        )

        # No retry loop here: we WANT the absence of a state change.
        # Wait a bounded window long enough for the worker to have
        # picked up + rejected the message.
        time.sleep(1.0)

        assert cache.liquid_capacitance_over_area == 0.0
        assert cache.filler_capacitance_over_area == 0.0
        assert not cache_changed_spy.is_set(), (
            "cache_changed must NOT fire on malformed payload"
        )
    finally:
        cache.observe(_handler, "cache_changed", remove=True)
