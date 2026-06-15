"""Headless tests for the executor lifecycle handlers (PR #468 / issue #398).

RealtimeModeHandler and LoggingHandler are execution-only handlers driven by
the once-per-run on_pre_protocol_start / on_post_protocol_end hooks. These
tests exercise them with a real ProtocolContext (prompt_gui runs inline when
qsignals is None) and patched app_globals / publish_message — no Qt, no Redis.
"""

import threading
from unittest.mock import patch

from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.step_context import ProtocolContext
from pluggable_protocol_tree.execution.lifecycle.realtime_mode import (
    RealtimeModeHandler, _RESTORE_REALTIME_SCRATCH_KEY,
)
from pluggable_protocol_tree.services.preferences import ProtocolPreferences
from microdrop_application.dialogs.pyface_wrapper import YES

_RT = "pluggable_protocol_tree.execution.lifecycle.realtime_mode"


def _proto(preview=False):
    return ProtocolContext(stop_event=threading.Event(),
                           pause_event=PauseEvent(), preview_mode=preview)


def _prefs(**overrides):
    p = ProtocolPreferences()
    for k, v in overrides.items():
        setattr(p, k, v)
    return p


# --- RealtimeModeHandler ---------------------------------------------------

def test_realtime_preview_contributes_nothing():
    h = RealtimeModeHandler(preferences=_prefs())
    ctx = _proto(preview=True)
    with patch(f"{_RT}.publish_message") as pub, patch(f"{_RT}.app_globals"):
        h.on_pre_protocol_start(ctx)
    assert ctx.pre_protocol_wait_s == 0.0
    pub.assert_not_called()
    assert _RESTORE_REALTIME_SCRATCH_KEY not in ctx.scratch


def test_realtime_off_enables_and_contributes_settle():
    h = RealtimeModeHandler(preferences=_prefs(realtime_mode_settling_time_s=2.0))
    ctx = _proto()
    with patch(f"{_RT}.app_globals") as ag, patch(f"{_RT}.publish_message") as pub:
        ag.get.return_value = False               # realtime currently OFF
        h.on_pre_protocol_start(ctx)
    pub.assert_called_once()                       # turned it on
    assert ctx.pre_protocol_wait_s == 2.0          # settle contributed
    assert ctx.scratch[_RESTORE_REALTIME_SCRATCH_KEY] is False  # restore=off


def test_realtime_on_prompt_disabled_follows_preference():
    h = RealtimeModeHandler(preferences=_prefs(
        prompt_to_restore_realtime_mode=False,
        keep_realtime_mode_after_protocol=True,
        realtime_mode_settling_time_s=1.0))
    ctx = _proto()
    with patch(f"{_RT}.app_globals") as ag, patch(f"{_RT}.publish_message") as pub:
        ag.get.return_value = True                 # already ON
        h.on_pre_protocol_start(ctx)
    pub.assert_not_called()                        # already on -> no enable
    assert ctx.scratch[_RESTORE_REALTIME_SCRATCH_KEY] is True
    assert ctx.pre_protocol_wait_s == 1.0


def test_realtime_on_prompt_keeps_per_dialog_answer():
    h = RealtimeModeHandler(preferences=_prefs(prompt_to_restore_realtime_mode=True))
    ctx = _proto()
    with patch(f"{_RT}.app_globals") as ag, patch(f"{_RT}.publish_message"), \
         patch(f"{_RT}.confirm", return_value=(YES, False)):
        ag.get.return_value = True
        h.on_pre_protocol_start(ctx)
    assert ctx.scratch[_RESTORE_REALTIME_SCRATCH_KEY] is True


def test_realtime_post_noop_when_pre_never_ran():
    """Cancelled-before-prep (or preview): no scratch entry -> no restore."""
    h = RealtimeModeHandler(preferences=_prefs())
    ctx = _proto()                                  # scratch empty
    with patch(f"{_RT}.publish_message") as pub:
        h.on_post_protocol_end(ctx)
    pub.assert_not_called()


def test_realtime_post_restores_off_when_not_keeping():
    h = RealtimeModeHandler(preferences=_prefs())
    ctx = _proto()
    ctx.scratch[_RESTORE_REALTIME_SCRATCH_KEY] = False
    with patch(f"{_RT}.publish_message") as pub:
        h.on_post_protocol_end(ctx)
    pub.assert_called_once()


def test_realtime_post_keeps_on_when_keeping():
    h = RealtimeModeHandler(preferences=_prefs())
    ctx = _proto()
    ctx.scratch[_RESTORE_REALTIME_SCRATCH_KEY] = True
    with patch(f"{_RT}.publish_message") as pub:
        h.on_post_protocol_end(ctx)
    pub.assert_not_called()


# --- LoggingHandler --------------------------------------------------------

def _logging_controller():
    from pluggable_protocol_tree.services.logging.controller import (
        ProtocolLoggingController,
    )
    return ProtocolLoggingController(
        settling_provider=lambda: 0.0, flush_scheduler=lambda c: None)


def test_logging_handler_starts_logging_with_built_context(tmp_path):
    from pluggable_protocol_tree.execution.lifecycle.logging import LoggingHandler
    import pluggable_protocol_tree.services.logging.listener as L

    controller = _logging_controller()
    handler = LoggingHandler(
        controller=controller,
        experiment_dir_provider=lambda: tmp_path,
        n_steps_provider=lambda: 3,
    )
    ctx = _proto()
    # Patch the app_globals the device-context trait defaults read so the
    # build doesn't touch Redis.
    with patch("pluggable_protocol_tree.services.logging.models.app_globals") as ag:
        ag.get.return_value = None
        handler.on_pre_protocol_start(ctx)
    try:
        assert controller._ingestion is not None
        assert controller._n_steps == 3
    finally:
        L.clear_active_logger()


def test_logging_handler_preview_is_noop(tmp_path):
    from pluggable_protocol_tree.execution.lifecycle.logging import LoggingHandler

    controller = _logging_controller()
    handler = LoggingHandler(
        controller=controller,
        experiment_dir_provider=lambda: tmp_path,
        n_steps_provider=lambda: 3,
    )
    ctx = _proto(preview=True)
    handler.on_pre_protocol_start(ctx)
    assert controller._ingestion is None
