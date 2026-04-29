"""Tests for CalibrationCache + the calibration_data_listener actor.

The actor function is invoked directly (no broker). Each test resets
the module-level singleton so ordering is irrelevant.
"""

import json

import pytest

from device_viewer.consts import CALIBRATION_DATA
from dropbot_protocol_controls.consts import CALIBRATION_LISTENER_ACTOR_NAME
from dropbot_protocol_controls.services.calibration_cache import (
    CalibrationCache,
    _on_calibration,
    cache,
)


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


def test_capacitance_per_unit_area_initial_returns_none():
    assert cache.capacitance_per_unit_area() is None


def test_capacitance_per_unit_area_after_update_returns_difference():
    cache.trait_set(
        liquid_capacitance_over_area=2.0,
        filler_capacitance_over_area=0.5,
    )
    assert cache.capacitance_per_unit_area() == pytest.approx(1.5)


def test_cache_changed_event_fires_on_mutation():
    fired = []

    def handler(event):
        fired.append(event)

    cache.observe(handler, "cache_changed")
    try:
        cache.cache_changed = True
    finally:
        cache.observe(handler, "cache_changed", remove=True)

    assert len(fired) == 1


def test_actor_happy_path_updates_cache_and_fires_event():
    fired = []
    cache.observe(lambda e: fired.append(e), "cache_changed")

    _on_calibration(
        json.dumps({
            "liquid_capacitance_over_area": 3.0,
            "filler_capacitance_over_area": 1.0,
        }),
        CALIBRATION_DATA,
    )

    assert cache.liquid_capacitance_over_area == pytest.approx(3.0)
    assert cache.filler_capacitance_over_area == pytest.approx(1.0)
    assert cache.capacitance_per_unit_area() == pytest.approx(2.0)
    assert len(fired) == 1


def test_actor_malformed_json_does_not_raise_and_does_not_fire():
    fired = []
    cache.observe(lambda e: fired.append(e), "cache_changed")

    _on_calibration("not-json", CALIBRATION_DATA)

    assert cache.liquid_capacitance_over_area == 0.0
    assert cache.filler_capacitance_over_area == 0.0
    assert fired == []


def test_actor_missing_keys_does_not_raise_and_does_not_fire():
    fired = []
    cache.observe(lambda e: fired.append(e), "cache_changed")

    _on_calibration(json.dumps({"unrelated": 1}), CALIBRATION_DATA)

    assert cache.liquid_capacitance_over_area == 0.0
    assert cache.filler_capacitance_over_area == 0.0
    assert fired == []


def test_actor_name_is_stable():
    assert CALIBRATION_LISTENER_ACTOR_NAME == "calibration_data_listener"


def test_calibration_cache_is_singleton_instance():
    assert isinstance(cache, CalibrationCache)
