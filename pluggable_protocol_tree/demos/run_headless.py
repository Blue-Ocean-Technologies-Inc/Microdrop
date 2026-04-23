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
"""

import logging
import sys
import time

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.models.row_manager import RowManager


logger = logging.getLogger(__name__)


def _build_protocol() -> RowManager:
    """A small protocol exercising flat steps + a repeating group."""
    cols = [
        make_type_column(),
        make_id_column(),
        make_name_column(),
        make_repetitions_column(),
        make_duration_column(),
    ]
    rm = RowManager(columns=cols)

    rm.add_step(values={"name": "Warmup", "duration_s": 0.5})

    # A group that repeats twice
    g = rm.add_group(name="LoopBody")
    rm.get_row(g).repetitions = 2
    rm.add_step(parent_path=g, values={"name": "InnerA", "duration_s": 0.3})
    rm.add_step(parent_path=g, values={"name": "InnerB", "duration_s": 0.3})

    # A step that repeats by itself
    s = rm.add_step(values={"name": "ThreeTimes", "duration_s": 0.2})
    rm.get_row(s).repetitions = 3

    rm.add_step(values={"name": "Cooldown", "duration_s": 0.5})
    return rm


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    rm = _build_protocol()
    n_steps = sum(1 for _ in rm.iter_execution_steps())
    logger.info("Built protocol with %d total steps after rep expansion",
                n_steps)

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


if __name__ == "__main__":
    sys.exit(main())
