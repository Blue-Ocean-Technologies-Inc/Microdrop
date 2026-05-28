from pyface.tasks.action.task_action import TaskWindowAction
from traits.trait_types import Str, Any

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from logger.logger_service import get_logger
logger = get_logger(__name__)


class DramatiqMessagePublishAction(TaskWindowAction):
    topic = Str(desc="topic this action connects to")
    message = Any(desc="message to publish")

    def perform(self, event=None):
        pre_routine_result = self.pre_perform()

        if pre_routine_result:
            publish_message(topic=self.topic, message=self.message)

        else:
            logger.warning(f"Pre perform failed: Action to publish {self.message} to topic {self.topic} not executed")
            return

        self.post_perform()

    ## Additional hooks for routines done pre/post perform

    def pre_perform(self) -> bool:
        """
        Add routine to perform fter performing the action. Return True to proceed to perform
        """
        return True

    def post_perform(self):
        """
        Add routine to perform before performing the action.
        """
        pass
