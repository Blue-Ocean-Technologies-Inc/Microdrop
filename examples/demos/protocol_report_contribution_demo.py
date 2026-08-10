"""Standalone demo: external plugins contributing protocol-report content.

Exercises the PROTOCOL_LOGGING_METADATA_CONTRIBUTION /
PROTOCOL_LOGGING_DATA_CONTRIBUTION topics end-to-end over redis/dramatiq,
without the GUI:

1. subscribes the protocol-tree logging listener to its topics on a
   MessageRouterActor (the same wiring the app uses),
2. starts a logging run and simulates two protocol steps with a few
   CAPACITANCE_UPDATED samples (the logger's core data),
3. plays the part of an external "heater plugin" publishing report
   metadata (firmware version, sample id) and per-step temperature rows
   through the validated contribution publishers in
   pluggable_protocol_tree.consts,
4. stops the run and prints the generated HTML report path.

In the report: the contributed metadata appears in the Metadata table, and
the contributed "Temperature (C)" column gets its own Data Summary row and
per-step Data Trends chart — no logger changes required.

Run: pixi run python -m examples.demos.protocol_report_contribution_demo
(redis-server must be on PATH or already running)
"""

import json
import logging
import tempfile
import threading
import time
from pathlib import Path

from microdrop_utils.broker_server_helpers import (
    configure_dramatiq_broker, dramatiq_workers_context, redis_server_context,
)

# The logging listener actor registers itself on the broker at import time,
# so the RedisBroker must be configured first (same pattern as the test
# conftests).
configure_dramatiq_broker()

from traits.api import Event, HasTraits

from dropbot_controller.consts import CAPACITANCE_UPDATED
from electrode_controller.consts import ELECTRODES_STATE_CHANGE
from microdrop_utils.dramatiq_pub_sub_helpers import (
    MessageRouterActor, publish_message,
)
from pluggable_protocol_tree.consts import (
    ACTOR_TOPIC_DICT, LOGGING_LISTENER_NAME,
    protocol_logging_data_contribution_publisher,
    protocol_logging_metadata_contribution_publisher,
)
import pluggable_protocol_tree.services.logging.listener  # noqa: F401 — registers the logging_listener actor
from pluggable_protocol_tree.services.logging.controller import (
    ProtocolLoggingController,
)
from pluggable_protocol_tree.services.logging.models import LoggingDeviceContext

N_STEPS = 2
SAMPLES_PER_STEP = 5
# Short settling delay so the post-stop flush (which builds the report)
# runs quickly; the real app reads this from ProtocolPreferences.
DEMO_SETTLING_SECONDS = 1.0
# Grace period for the dramatiq workers to route in-flight messages before
# the run is stopped / between steps.
ROUTING_DRAIN_SECONDS = 1.0


class _DemoExecutorSignals(HasTraits):
    """Stand-in for the executor's signals object: firing step_started with
    a (row, step_index, step_total) tuple is exactly what
    ProtocolLoggingController.attach observes."""
    step_started = Event


class _DemoRow:
    """Minimal protocol row — the logger only reads row.uuid."""
    def __init__(self, uuid: str):
        self.uuid = uuid


def main():
    experiment_dir = Path(tempfile.mkdtemp(prefix="protocol_report_demo_"))
    print(f"Experiment directory: {experiment_dir}")

    # Wire the logging listener exactly like the app: subscribe it to its
    # ACTOR_TOPIC_DICT topics (core + contribution) on the message router.
    router = MessageRouterActor()
    for topic in ACTOR_TOPIC_DICT[LOGGING_LISTENER_NAME]:
        router.message_router_data.add_subscriber_to_topic(
            topic=topic, subscribing_actor_name=LOGGING_LISTENER_NAME)

    report_done = threading.Event()
    report_paths = []

    def _on_report(path):
        report_paths.append(path)
        report_done.set()

    controller = ProtocolLoggingController(
        settling_provider=lambda: DEMO_SETTLING_SECONDS,
        completion_callback=_on_report)
    signals = _DemoExecutorSignals()
    controller.attach(signals)

    context = LoggingDeviceContext(
        experiment_directory=experiment_dir,
        device_svg_path=None,                      # no SVG -> no heatmap
        channel_areas={ch: 1.5 for ch in range(8)},
        capacitance_per_unit_area=2.0)

    controller.start_logging(context, n_steps=N_STEPS, preview_mode=False)

    # --- external "heater plugin" contributes report metadata -------------
    protocol_logging_metadata_contribution_publisher.publish(
        {"Heater Firmware": "v2.1.0", "Sample ID": "S-042"})

    # --- simulated run: core capacitance + contributed temperature rows ---
    instrument_time_us = 0
    for step_number in range(1, N_STEPS + 1):
        print(f"Step {step_number}/{N_STEPS}")
        signals.step_started = (
            _DemoRow(f"demo-step-{step_number}"), step_number - 1, N_STEPS)
        publish_message(
            message=json.dumps({"channels": [step_number, step_number + 1]}),
            topic=ELECTRODES_STATE_CHANGE)
        time.sleep(ROUTING_DRAIN_SECONDS)   # actuation context before samples
        for sample in range(SAMPLES_PER_STEP):
            instrument_time_us += 50_000
            publish_message(
                message=json.dumps({
                    "capacitance": f"{12.0 + step_number + 0.1 * sample}pF",
                    "voltage": "100V",
                    "instrument_time_us": instrument_time_us,
                    "reception_time": int(time.time()),
                }),
                topic=CAPACITANCE_UPDATED)
            protocol_logging_data_contribution_publisher.publish(
                {"Temperature (C)": 60.0 + step_number + 0.2 * sample})
        time.sleep(ROUTING_DRAIN_SECONDS)

    controller.stop_logging()

    if report_done.wait(timeout=30) and report_paths and report_paths[0]:
        print(f"\nReport written: {report_paths[0]}")
        print("Open it and look for:")
        print("  - Metadata table rows 'Heater Firmware' / 'Sample ID'")
        print("  - 'Temperature (C)' in Data Summary and Data Trends")
    else:
        print("\nReport generation failed — see log output above.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    with redis_server_context():
        with dramatiq_workers_context():
            main()
