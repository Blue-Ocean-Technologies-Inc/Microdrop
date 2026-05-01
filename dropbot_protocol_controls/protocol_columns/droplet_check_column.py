"""PPT-8: per-step droplet check column. After a step's phases complete,
the handler publishes DETECT_DROPLETS, awaits the backend's
DROPLETS_DETECTED reply, and on missing channels drives a UI confirm
dialog via topic round-trip. Mirrors PPT-7's force_column.py single-file
layout: pure helper + model + view + factory + handler.
"""

import json

from traits.api import Bool, Str

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from dropbot_controller.consts import DETECT_DROPLETS, DROPLETS_DETECTED

from ..consts import (
    DROPLET_CHECK_DECISION_REQUEST,
    DROPLET_CHECK_DECISION_RESPONSE,
)


logger = get_logger(__name__)


def expected_channels_for_step(row, electrode_to_channel: dict) -> list:
    """Channels we expect droplets on after this step's phases finish.

    Mirrors legacy _get_expected_droplet_channels
    (protocol_runner_controller.py:1763): the union of
    (statically activated electrodes) and (the LAST electrode of each
    route — that's where the droplet ends up). Returns a sorted unique
    list of int channels. Unknown electrode IDs are silently dropped
    rather than raising — same behavior as legacy.
    """
    expected = set()
    for eid in (row.electrodes or []):
        ch = electrode_to_channel.get(eid)
        if ch is not None:
            expected.add(int(ch))
    for route in (row.routes or []):
        if route:
            ch = electrode_to_channel.get(route[-1])
            if ch is not None:
                expected.add(int(ch))
    return sorted(expected)


class DropletCheckColumnModel(BaseColumnModel):
    """Per-step Bool: 'verify expected droplets after this step's phases'.
    Default True; user can disable per-step via header right-click on the
    hidden column."""

    col_id        = Str("check_droplets")
    col_name      = Str("Check Droplets")
    default_value = Bool(True)

    def trait_for_row(self):
        return Bool(True)


class DropletCheckColumnView(CheckboxColumnView):
    """Hidden by default — surfaces via header right-click. Same posture
    as PPT-3's trail/loop knob columns."""

    renders_on_group  = False
    hidden_by_default = True


class DropletCheckHandler(BaseColumnHandler):
    """Per-step droplet detection handler — runs in `on_post_step`."""

    priority        = 80
    wait_for_topics = [DROPLETS_DETECTED, DROPLET_CHECK_DECISION_RESPONSE]

    def on_post_step(self, row, ctx):
        if not row.check_droplets:
            return

        electrode_to_channel = ctx.protocol.scratch.get("electrode_to_channel", {})
        expected = expected_channels_for_step(row, electrode_to_channel)
        if not expected:
            return

        publish_message(topic=DETECT_DROPLETS, message=json.dumps(expected))
        try:
            ack_raw = ctx.wait_for(DROPLETS_DETECTED, timeout=12.0)
        except TimeoutError:
            # Backend handles its own internal retries; log + proceed
            # mirrors legacy behavior on the timeout path.
            logger.warning(
                f"Droplet detection timed out for step {row.uuid}; proceeding"
            )
            return
        ack = json.loads(ack_raw)

        if not ack.get("success"):
            # Surface backend errors (no proxy, hardware fault, etc.) to
            # the user via the same failure dialog as missing channels —
            # `detected` becomes a single error string, which is set-
            # disjoint from `expected` (ints) so every expected channel
            # ends up in `missing`. The dialog formatter renders the
            # string in the Detected row so the user sees what went wrong
            # and can choose Continue or Stay Paused.
            logger.warning(
                f"Droplet detection backend error on step {row.uuid}: "
                f"{ack.get('error')}"
            )
            detected = [f"<b>ERROR!</b> \n\n {ack.get('error')}"]
        else:
            detected = [int(c) for c in ack.get("detected_channels", [])]

        missing = sorted(set(expected) - set(detected))
        if not missing:
            return

        # Failure path: emit protocol_paused BEFORE the dialog wait so the
        # UI freezes step/phase timers immediately. Without this the
        # tick timer keeps incrementing while the dialog is up because
        # step_finished hasn't fired yet. Qt signals are thread-safe to
        # emit from worker threads.
        qsignals = ctx.protocol.qsignals
        if qsignals is not None:
            qsignals.protocol_paused.emit()

        publish_message(
            topic=DROPLET_CHECK_DECISION_REQUEST,
            message=json.dumps({
                "step_uuid": row.uuid,
                "expected":  expected,
                "detected":  detected,
                "missing":   missing,
            }),
        )
        # 24h is "effectively infinite" for a user-facing dialog;
        # stop_event is the real cancellation path. wait_for requires
        # a finite float — None would crash deadline math.
        decision_raw = ctx.wait_for(
            DROPLET_CHECK_DECISION_RESPONSE,
            timeout=86_400.0,
            predicate=lambda payload: json.loads(payload).get("step_uuid") == row.uuid,
        )
        decision = json.loads(decision_raw).get("choice")
        logger.info(f"[droplet-check] step {row.uuid} decision={decision!r}")
        if decision == "pause":
            # Set pause_event; the executor's main loop sees it at the
            # next step boundary and blocks on wait_cleared(). Do NOT
            # emit protocol_resumed — the UI stays in the paused state
            # we set above until the user clicks Resume on the toolbar.
            pe = ctx.protocol.pause_event
            if pe is not None:
                pe.set()
            else:
                logger.warning(
                    "[droplet-check] PAUSE chosen but pause_event is None; "
                    "protocol will NOT actually pause"
                )
            return
        # "continue" — unfreeze the UI; executor proceeds to next step.
        if qsignals is not None:
            qsignals.protocol_resumed.emit()


def make_droplet_check_column() -> Column:
    return Column(
        model   = DropletCheckColumnModel(),
        view    = DropletCheckColumnView(),
        handler = DropletCheckHandler(),
    )
