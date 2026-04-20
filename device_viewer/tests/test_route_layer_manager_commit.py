from device_viewer.models.route import RouteLayerManager


EXEC_PARAMS = {
    "duration": 1.5,
    "repetitions": 3,
    "repeat_duration": 0,
    "trail_length": 2,
    "trail_overlay": 1,
    "soft_start": True,
    "soft_terminate": False,
}


def _apply(mgr, params):
    mgr.apply_execution_params(params)


def test_commit_disabled_when_no_baseline():
    mgr = RouteLayerManager()
    assert mgr.commit_enabled is False


def test_commit_disabled_when_equal_to_baseline():
    mgr = RouteLayerManager()
    _apply(mgr, EXEC_PARAMS)
    assert mgr.commit_enabled is False


def test_commit_enabled_when_any_param_diverges():
    mgr = RouteLayerManager()
    _apply(mgr, EXEC_PARAMS)
    mgr.duration = 5.0
    assert mgr.commit_enabled is True


def test_commit_enabled_resets_after_rebaseline():
    mgr = RouteLayerManager()
    _apply(mgr, EXEC_PARAMS)
    mgr.duration = 5.0
    assert mgr.commit_enabled is True

    # Re-baseline to current values (what commit handler does)
    mgr.mark_params_committed()
    assert mgr.commit_enabled is False
