"""Demo of the ProtocolSession API.

The runtime payoff: once a protocol JSON exists somewhere on disk,
this is the entire script needed to load + run it:

    from pluggable_protocol_tree.session import ProtocolSession

    with ProtocolSession.from_file('my_protocol.json',
                                   with_demo_hardware=True) as session:
        session.start()
        session.wait()

ProtocolSession resolves the column factories from the recorded
``cls`` qualnames, restores ``protocol_metadata``, sets up the
in-process demo electrode_responder + Dramatiq worker, and exposes
the executor's ``start/pause/resume/stop/wait`` controls.

This demo writes a small sample protocol to the temp dir on each
run, then loads it back through the session API and exercises a
pause/resume cycle so you can see all the controls work.

Run: pixi run python -m pluggable_protocol_tree.demos.run_session_demo
"""

import json
import logging
import sys
import tempfile
import time
from pathlib import Path

import dramatiq

# Strip Prometheus middleware up front (matches the other demos);
# without this, every actor publish raises inside its
# after_process_message hook and silently drops messages.
for _m in list(dramatiq.get_broker().middleware):
    if _m.__module__ == "dramatiq.middleware.prometheus":
        dramatiq.get_broker().middleware.remove(_m)

from pluggable_protocol_tree.builtins.duration_column import (
    make_duration_column,
)
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
from pluggable_protocol_tree.builtins.repetitions_column import (
    make_repetitions_column,
)
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.soft_end_column import make_soft_end_column
from pluggable_protocol_tree.builtins.soft_start_column import (
    make_soft_start_column,
)
from pluggable_protocol_tree.builtins.trail_length_column import (
    make_trail_length_column,
)
from pluggable_protocol_tree.builtins.trail_overlay_column import (
    make_trail_overlay_column,
)
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import ELECTRODES_STATE_CHANGE
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.session import ProtocolSession


logger = logging.getLogger(__name__)


# Phase spy: subscribed to ELECTRODES_STATE_CHANGE so we can print
# every phase the executor publishes. Unrelated to ProtocolSession
# itself -- just here to make the demo's progress visible.
PHASE_SPY_ACTOR_NAME = "ppt_session_demo_phase_spy"


@dramatiq.actor(actor_name=PHASE_SPY_ACTOR_NAME, queue_name="default")
def _phase_spy(message: str, topic: str, timestamp: float = None):
    try:
        payload = json.loads(message)
    except (TypeError, ValueError):
        return
    print(f"  phase: electrodes={payload['electrodes']} "
          f"channels={payload['channels']}", flush=True)


def _build_sample_protocol_file(path: Path) -> None:
    """Write a sample 4-step protocol (static pad, route walk, repeating
    pulse, cooldown) to ``path`` so the rest of the demo has something
    to load. In real use this file would be written by your protocol
    editor / GUI / batch generator."""
    cols = [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_trail_length_column(), make_trail_overlay_column(),
        make_soft_start_column(), make_soft_end_column(),
        make_repeat_duration_column(), make_linear_repeats_column(),
    ]
    rm = RowManager(columns=cols)
    rm.protocol_metadata["electrode_to_channel"] = {
        f"e{i:02d}": i for i in range(25)
    }
    rm.add_step(values={
        "name": "Hold three-cell pad",
        "duration_s": 0.2,
        "electrodes": ["e00", "e01", "e02"],
    })
    rm.add_step(values={
        "name": "Walk top row",
        "duration_s": 0.2,
        "routes": [["e00", "e01", "e02", "e03", "e04"]],
        "trail_length": 1,
    })
    rm.add_step(values={
        "name": "Walk diagonal",
        "duration_s": 0.2,
        "routes": [["e00", "e06", "e12", "e18", "e24"]],
        "trail_length": 1,
    })
    rm.add_step(values={"name": "Cooldown", "duration_s": 0.2})

    with open(path, "w", encoding="utf-8") as f:
        json.dump(rm.to_json(), f, indent=2)


def _subscribe_phase_spy(session: ProtocolSession) -> None:
    """Subscribe the demo phase_spy actor to the actuation topic via
    the session's router. Lets the script print phases as they fire."""
    if session._router is None:
        return
    try:
        session._router.message_router_data.remove_subscriber_from_topic(
            topic=ELECTRODES_STATE_CHANGE,
            subscribing_actor_name=PHASE_SPY_ACTOR_NAME,
        )
    except Exception:
        pass
    session._router.message_router_data.add_subscriber_to_topic(
        topic=ELECTRODES_STATE_CHANGE,
        subscribing_actor_name=PHASE_SPY_ACTOR_NAME,
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 1. Save a sample protocol file (in real use this already exists).
    path = Path(tempfile.gettempdir()) / "ppt_session_demo_protocol.json"
    _build_sample_protocol_file(path)
    print(f"\nWrote sample protocol to: {path}\n")

    # 2. Load + run via the ProtocolSession API. This is the part a
    #    user-written runner script would actually contain.
    with ProtocolSession.from_file(str(path),
                                   with_demo_hardware=True) as session:
        n_steps = len(session.manager.root.children)
        print(f"Loaded {n_steps} top-level steps "
              f"({len(session.manager.columns)} columns resolved "
              f"dynamically from the file).")
        _subscribe_phase_spy(session)

        # 3. Drive it like a programmable executor.
        print("\nStarting protocol...")
        session.start()

        # Demonstrate pause/resume mid-run.
        time.sleep(0.5)
        print("\n>> Pausing (effective at next step boundary) <<")
        session.pause()
        time.sleep(1.0)
        print(">> Resuming <<\n")
        session.resume()

        if not session.wait(timeout=30.0):
            print("Protocol still running after 30s, stopping...")
            session.stop()
            session.wait(timeout=5.0)

    print("\nDone -- ProtocolSession context exited cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
