from pyface.tasks.action.task_action import TaskWindowAction
from traits.trait_types import Str, Any

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message


class DramatiqMessagePublishAction(TaskWindowAction):
    topic = Str(desc="topic this action connects to")
    message = Any(desc="message to publish")

    def perform(self, event=None):
        publish_message(topic=self.topic, message=self.message)
