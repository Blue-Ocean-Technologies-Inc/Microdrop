"""Headless protocol-execution demo — no Qt window, just log messages.

Demonstrates the executor's scripting API:

    ex = ProtocolExecutor.execute(row_manager, blocking=False)
    ex.pause();  time.sleep(2);  ex.resume()
    ex.stop()
    ex.wait()

Run:
    pixi run python -m pluggable_protocol_tree.demos.run_headless

Press Ctrl+C to stop the running protocol.

The executor itself is Qt-aware (ExecutorSignals subclasses QObject) but
no QApplication / event loop is required — Qt direct-connected slots
fire synchronously on the worker thread. So this script runs anywhere
PySide6 can be imported, headless servers included.

Redis behaviour
---------------
If a Redis broker is reachable, the protocol includes the demo
ack-roundtrip column (publishes a "set state" request to one topic and
blocks via ctx.wait_for() for the ack on a different topic; the
duration timer only starts ticking once the ack arrives). The script
spins up an in-process Dramatiq Worker so the responder + listener
actors actually fire, then stops it on exit.

If Redis isn't reachable, the script logs a warning and runs the
protocol without that column — still demonstrates the executor's
scripting API end-to-end.
"""

import logging
import sys
import threading
import time

import dramatiq

# Strip the Prometheus middleware before any actor publishes — the
# default install in this env raises 'Prometheus object has no attribute
# message_durations' inside its after_process_message hook, which
# corrupts the dispatch chain and turns every subsequent publish into
# a silent drop. (The GUI demo applies the same workaround.)
from microdrop_utils.broker_server_helpers import remove_middleware_from_dramatiq_broker
remove_middleware_from_dramatiq_broker(middleware_name="dramatiq.middleware.prometheus", broker=dramatiq.get_broker())

import json

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.linear_repeats_column import (
    make_linear_repeats_column,
)
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repeat_duration_column import (
    make_repeat_duration_column,
)
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.soft_end_column import make_soft_end_column
from pluggable_protocol_tree.builtins.soft_start_column import make_soft_start_column
from pluggable_protocol_tree.builtins.trail_length_column import (
    make_trail_length_column,
)
from pluggable_protocol_tree.builtins.trail_overlay_column import (
    make_trail_overlay_column,
)
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.demos.ack_roundtrip_column import (
    DEMO_APPLIED_TOPIC, DEMO_REQUEST_TOPIC, RESPONDER_ACTOR_NAME,
    make_ack_roundtrip_column,
)
from pluggable_protocol_tree.demos.electrode_responder import (
    DEMO_RESPONDER_ACTOR_NAME,
)
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.models.row_manager import RowManager


logger = logging.getLogger(__name__)


PHASE_LOG_ACTOR_NAME = "ppt_headless_phase_log"


@dramatiq.actor(actor_name=PHASE_LOG_ACTOR_NAME, queue_name="default")
def _log_phase(message: str, topic: str, timestamp: float = None):
    """Spies on every actuation phase the executor publishes so the
    headless caller sees what the hardware would receive."""
    payload = json.loads(message)
    print(f"  phase: electrodes={payload['electrodes']} "
          f"channels={payload['channels']}")


_SUBSCRIPTIONS = (
    (DEMO_REQUEST_TOPIC, RESPONDER_ACTOR_NAME),
    (DEMO_APPLIED_TOPIC, "pluggable_protocol_tree_executor_listener"),
    # PPT-3: electrode actuation chain + a console-spy on every phase.
    (ELECTRODES_STATE_CHANGE, DEMO_RESPONDER_ACTOR_NAME),
    (ELECTRODES_STATE_APPLIED,
     "pluggable_protocol_tree_executor_listener"),
    (ELECTRODES_STATE_CHANGE, PHASE_LOG_ACTOR_NAME),
)


def _setup_dramatiq_routing():
    """Best-effort Dramatiq + Redis setup.

    Returns ``(worker, router, ok)``: ``worker`` is a started
    ``Dramatiq.Worker`` or None; ``router`` is the
    ``MessageRouterActor`` instance for cleanup; ``ok`` is True iff the
    routing was registered (i.e. the ack-roundtrip column will succeed).

    Subscriptions are removed-then-re-added so a previous broken run
    (e.g. one that crashed before its finally block could clean up)
    doesn't leave stale subscribers in the Redis hash that double-fire
    or absorb messages we expect.
    """
    try:
        import dramatiq
        from dramatiq import Worker
        from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterActor

        router = MessageRouterActor()
        for topic, actor_name in _SUBSCRIPTIONS:
            try:
                router.message_router_data.remove_subscriber_from_topic(
                    topic=topic, subscribing_actor_name=actor_name,
                )
            except Exception:
                pass     # not subscribed → nothing to remove
            router.message_router_data.add_subscriber_to_topic(
                topic=topic, subscribing_actor_name=actor_name,
            )
        worker = Worker(dramatiq.get_broker(), worker_timeout=100)
        worker.start()
        logger.info("Dramatiq worker started; ack-roundtrip column enabled")
        return worker, router, True
    except Exception as e:
        logger.warning(
            "Dramatiq routing setup failed (Redis not running?): %s — "
            "ack-roundtrip column will be omitted from the protocol", e,
        )
        return None, None, False


def _teardown_dramatiq_routing(worker, router):
    """Stop the worker and remove our subscriptions from the Redis hash.
    Called from main()'s finally so subsequent demo runs start clean."""
    if router is not None:
        for topic, actor_name in _SUBSCRIPTIONS:
            try:
                router.message_router_data.remove_subscriber_from_topic(
                    topic=topic, subscribing_actor_name=actor_name,
                )
            except Exception:
                logger.exception("Error removing subscription %s/%s",
                                 topic, actor_name)
    if worker is not None:
        try:
            worker.stop()
        except Exception:
            logger.exception("Error stopping demo Dramatiq worker")


def _build_protocol(include_ack_column: bool) -> RowManager:
    """A small protocol exercising flat steps + a repeating group +
    the PPT-3 electrodes/routes columns + optionally the older
    publish/wait_for round-trip column."""
    cols = [
        make_type_column(),
        make_id_column(),
        make_name_column(),
        make_repetitions_column(),
        make_duration_column(),
        # PPT-3 — the headless electrode-actuation columns.
        make_electrodes_column(),
        make_routes_column(),
        make_trail_length_column(),
        make_trail_overlay_column(),
        make_soft_start_column(),
        make_soft_end_column(),
        make_repeat_duration_column(),
        make_linear_repeats_column(),
    ]
    if include_ack_column:
        cols.append(make_ack_roundtrip_column())
    rm = RowManager(columns=cols)

    # PPT-3 — the per-protocol electrode→channel mapping the
    # RoutesHandler reads from ProtocolContext.scratch when resolving
    # actuation channels for each phase.
    rm.protocol_metadata["electrode_to_channel"] = {
        f"e{i:02d}": i for i in range(25)
    }

    # Step 1 — pure static actuation: hold three pads for the dwell.
    rm.add_step(values={
        "name": "Hold three-cell pad",
        "duration_s": 0.5,
        "electrodes": ["e00", "e01", "e02"],
    })

    # A group that repeats twice — each child walks a short route
    # (4 phases at trail_length=1) before its dwell timer.
    g = rm.add_group(name="LoopBody")
    rm.get_row(g).repetitions = 2
    rm.add_step(parent_path=g, values={
        "name": "Walk top row",
        "duration_s": 0.3,
        "routes": [["e00", "e01", "e02", "e03", "e04"]],
        "trail_length": 1,
    })
    rm.add_step(parent_path=g, values={
        "name": "Walk diagonal",
        "duration_s": 0.3,
        "routes": [["e00", "e06", "e12", "e18", "e24"]],
        "trail_length": 1,
    })

    # A self-repeating step that holds two electrodes 3 times.
    s = rm.add_step(values={
        "name": "Pulse pair",
        "duration_s": 0.2,
        "electrodes": ["e12", "e13"],
    })
    rm.get_row(s).repetitions = 3

    rm.add_step(values={"name": "Cooldown", "duration_s": 0.5})

    if include_ack_column:
        # Override the State value on a few rows so the per-step log
        # lines show different request payloads (the responder echoes
        # them back in its "applied: ..." reply). Top-level positions:
        # 0=Hold pad, 1=LoopBody (group), 2=Pulse pair, 3=Cooldown.
        rm.get_row((0,)).state = "HV=on"
        rm.get_row((1, 0)).state = "HV=ramp"   # Walk top row inside LoopBody
        rm.get_row((2,)).state = "HV=peak"
        rm.get_row((3,)).state = "HV=off"

    return rm


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    worker, router, redis_ok = _setup_dramatiq_routing()
    try:
        rm = _build_protocol(include_ack_column=redis_ok)
        n_steps = sum(1 for _ in rm.iter_execution_steps())
        logger.info(
            "Built protocol: %d total steps after rep expansion (ack-column %s)",
            n_steps, "ENABLED" if redis_ok else "DISABLED — no Redis",
        )

        # Start non-blocking so we can still field Ctrl+C while the
        # protocol runs on the worker thread.
        ex = ProtocolExecutor.execute(rm, blocking=False)
        print("Protocol running headlessly. Press Ctrl+C to stop.")
        try:
            ex.wait()
        except KeyboardInterrupt:
            print("\nKeyboardInterrupt — requesting stop")
            ex.stop()
            ex.wait(timeout=5.0)
            return 130   # standard SIGINT exit code
        return 0
    finally:
        _teardown_dramatiq_routing(worker, router)


if __name__ == "__main__":
    sys.exit(main())
