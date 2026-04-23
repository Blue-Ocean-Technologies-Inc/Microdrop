"""Demo column with publish → wait_for round-trip via Dramatiq.

Mimics what production hardware columns (PPT-3+ Voltage / Routes /
Electrodes) will do: publish a state-set request to a topic, block
on ctx.wait_for() until the ack arrives on a different topic, then
return so the next priority bucket (DurationColumnHandler at 90) can
run its dwell sleep.

The responder is an in-process Dramatiq actor that sleeps for a
simulated settle time and publishes confirmation. Requires Redis +
a worker; the demo's run_widget starts both. If Redis isn't reachable
the wait_for will raise TimeoutError → protocol_error dialog.
"""

import logging
import time

import dramatiq
from traits.api import Str

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.string_edit import StringEditColumnView


logger = logging.getLogger(__name__)

DEMO_REQUEST_TOPIC = "microdrop/protocol_tree/demo_state_request"
DEMO_APPLIED_TOPIC = "microdrop/protocol_tree/demo_state_applied"
RESPONDER_ACTOR_NAME = "ppt_demo_state_responder"
DEMO_ACK_DELAY_S = 0.3


@dramatiq.actor(actor_name=RESPONDER_ACTOR_NAME, queue_name="default")
def _demo_state_responder(message: str, topic: str, timestamp: float = None):
    """Hardware-controller stand-in. Sleeps DEMO_ACK_DELAY_S (simulating
    settle time) then publishes confirmation back through the router."""
    logger.info("[demo responder] received %r on %s, applying...",
                message, topic)
    time.sleep(DEMO_ACK_DELAY_S)
    publish_message(message=f"applied: {message}", topic=DEMO_APPLIED_TOPIC)
    logger.info("[demo responder] published applied")


class AckRoundtripModel(BaseColumnModel):
    def trait_for_row(self):
        return Str(str(self.default_value or "HV=on"))


class AckRoundtripHandler(BaseColumnHandler):
    """Publishes the row's State value and waits for the ack before
    returning. Priority 30 keeps this in an earlier bucket than
    DurationColumnHandler (90) — sequential, not parallel — so the
    duration timer only starts ticking once the ack arrives."""
    priority = 30
    wait_for_topics = [DEMO_APPLIED_TOPIC]

    def on_step(self, row, ctx):
        msg = self.model.get_value(row)
        logger.info("[apply state] requesting %r", msg)
        publish_message(message=str(msg), topic=DEMO_REQUEST_TOPIC)
        payload = ctx.wait_for(DEMO_APPLIED_TOPIC, timeout=5.0)
        logger.info("[apply state] ack received %r", payload)


def make_ack_roundtrip_column():
    return Column(
        model=AckRoundtripModel(
            col_id="state", col_name="State", default_value="HV=on",
        ),
        view=StringEditColumnView(),
        handler=AckRoundtripHandler(),
    )
