"""Toy demo column — publishes a log line on every on_step.

Lives in demos/, not builtins/, because it has no production purpose.
The Redis integration test in tests_with_redis_server_need/ uses this
column to prove the round-trip publish → listener → mailbox → wait_for
path works against a real broker.
"""

from traits.api import Str

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.string_edit import (
    StringEditColumnView,
)


DEMO_MESSAGE_TOPIC = "microdrop/protocol_tree/demo_message"


class MessageColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Str("hello", desc="Message published when this step runs")


class MessageColumnHandler(BaseColumnHandler):
    priority = 50
    wait_for_topics = []        # demo doesn't wait

    def on_step(self, row, ctx):
        msg = self.model.get_value(row)
        publish_message(
            topic=DEMO_MESSAGE_TOPIC,
            message={
                "row_uuid": row.uuid,
                "name": row.name,
                "msg": msg,
            },
        )


def make_message_column():
    return Column(
        model=MessageColumnModel(
            col_id="demo_message", col_name="Message", default_value="hello",
        ),
        view=StringEditColumnView(),
        handler=MessageColumnHandler(),
    )
