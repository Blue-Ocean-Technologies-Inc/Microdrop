# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""One accepted self-test run's board: the adapter between the pure
choreography (``self_test_choreography.execute_run``) and the composed
Portable DropBot controller."""

# Standard library imports.
import threading
import time

# Third-party imports.
from dropbot_portable.self_test import self_test

# Enthought library imports.
from traits.api import Any, Dict, Float, HasTraits, Instance, Int, List, Str

# Microdrop package imports.
from portable_dropbot_self_tests.consts import (
    self_test_progress_publisher,
    self_test_result_publisher,
)

# Local imports.
from .consts import HV_ENABLE_STATUS_OFF
from .self_test_choreography import hv_status_byte
from .self_test_results import result_payload, strip_traceback, write_result_json

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The vendor tests' step events are published at most this often.
PROGRESS_STEP_INTERVAL_S = 0.2


class SelfTestBoard(HasTraits):
    """One accepted run's board, as ``execute_run`` drives it: each step
    holds the controller's proxy lock for that step only and publishes the
    run's progress and results."""

    #: The composed Portable DropBot controller running the run.
    controller = Any()
    #: The driver session captured when the run started.
    bot = Any()
    run_id = Str()
    tests = List(Str)
    test_kwargs = Dict()
    cancel = Instance(threading.Event)
    #: The run's JSON folder; None when it could not be resolved.
    directory = Any(None)
    stamp = Str()

    #: Run position of the test being executed (progress index).
    _test_index = Int(0)
    #: Monotonic time of the last published step event (throttle).
    _last_step_time = Float(0.0)

    def hv_off(self, step):
        self._publish_progress(step.index, phase="choreography", text=step.text)
        ok, reply = self.controller._proxy_call(
            "self-test: HV off", lambda: self.bot.sig.hv_enable(0, 0)
        )

        return reply if ok else None

    def move_pads(self, step):
        """HV off (confirmed), the pad move and its PUSHPAD_READ read-back,
        all under one proxy-lock span: nothing can re-enable the HV between
        the confirmation and the move. The move itself skips the lock
        (``_motion_call``) without releasing this span. After an E-STOP no
        move is sent, as the vendor runner's halt."""
        self._publish_progress(step.index, phase="choreography", text=step.text)

        with self.controller._proxy_lock:
            ok, reply = self.controller._proxy_call(
                "self-test: HV off before the pad move",
                lambda: self.bot.sig.hv_enable(0, 0),
            )
            status = hv_status_byte(reply) if ok else None

            if status != HV_ENABLE_STATUS_OFF:
                return False, None, f"HV off not confirmed (reply {status!r})"

            halt = self.controller._self_test_halt_reason

            if halt:
                return False, None, f"{halt}: the pads are left where they are"

            accepted = self.controller._set_pogo(step.target)
            ok, read_back = self.controller._proxy_call(
                "self-test: pad read-back", lambda: self.bot.uart.getPogo()
            )

        return accepted, read_back if ok else None, ""

    def run_test(self, step):
        """One ``self_test(tests=[name])`` call; publishes its result."""
        name = step.test
        overrides = self.test_kwargs.get(name)
        extra = {"test_kwargs": {name: dict(overrides)}} if overrides else {}

        self._test_index = step.index
        ok, results = self.controller._proxy_call(
            f"self-test {name}",
            lambda: self_test(
                self.bot,
                tests=[name],
                progress=self._on_vendor_progress,
                cancel=self.cancel,
                **extra,
            ),
        )

        if ok:
            raw = results.get(name) if isinstance(results, dict) else None

            # No result is only normal when the cancel landed before the start.
            if raw is None and not self.cancel.is_set():
                raw = {"error": "no result"}
        else:
            # The call itself failed (the vendor records a test's own errors):
            # an OSError here is the link going, which the run then stops on.
            raw = {"error": repr(results) if results is not None else "not connected"}

        if raw is not None:
            self._publish_result(name, raw)

        return raw

    def between_steps(self):
        """Refresh the status panes; a failed refresh never ends the run."""

        if self.link_lost():
            return

        try:
            self.controller._publish_status_snapshot()
        except Exception as error:
            logger.warning(f"Self-test status refresh failed: {error}")

    def link_lost(self):
        return (
            not self.controller.portable_dropbot_connection_active
            or self.controller.proxy is not self.bot
        )

    def _on_vendor_progress(self, event):
        """The vendor's progress callback (this run's thread): index/total
        rewritten to span the run, step events throttled."""
        phase = event.get("phase")

        if phase not in ("start", "step", "done"):
            return

        now = time.monotonic()
        final_step = event.get("step") == event.get("steps")

        if phase == "step" and not final_step:
            if now - self._last_step_time < PROGRESS_STEP_INTERVAL_S:
                return

            self._last_step_time = now

        self._publish_progress(
            self._test_index,
            phase=phase,
            name=str(event.get("name") or self.tests[self._test_index]),
            step=event.get("step"),
            steps=event.get("steps"),
            error=bool(event.get("error")),
            cancelled=bool(event.get("cancelled")),
        )

    def _publish_progress(self, index, **fields):
        """Progress is informational: a failed publish is logged, never
        allowed to fail or skip hardware work."""

        try:
            self_test_progress_publisher.publish(
                {
                    "run_id": self.run_id,
                    "index": index,
                    "total": len(self.tests),
                    **fields,
                }
            )
        except Exception as error:
            logger.error(f"Self-test progress not published: {error}")

    def _publish_result(self, name, raw):
        result = strip_traceback(name, raw)
        path = write_result_json(name, result, self.directory, self.stamp)

        try:
            self_test_result_publisher.publish(
                result_payload(self.run_id, name, result, path)
            )
        except Exception as error:
            logger.error(f"Self-test {name} result not published: {error}")
