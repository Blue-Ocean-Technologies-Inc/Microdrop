from pyface.action.api import Action
from pyface.tasks.action.api import SGroup
from traits.api import Str


class ShowSendFeedbackAction(Action):
    name = Str("Send &Feedback...")
    tooltip = "Send feedback to the development team"

    def perform(self, event):
        from .feedback_dialog import SendFeedbackDialog

        dialog = SendFeedbackDialog(parent=event.task.window.control)
        dialog.exec_()


def menu_factory():
    return SGroup(
        ShowSendFeedbackAction(),
        id="send_feedback",
    )
