import webbrowser

from pyface.action.api import Action
from pyface.tasks.action.api import SGroup, SMenu
from traits.api import Str

from .consts import GITHUB_ISSUES_URL, SCIBOTS_URL


class AboutMicrodropAction(Action):
    name = Str("&About MicroDrop...")
    tooltip = "Learn about MicroDrop's architecture and capabilities"

    def perform(self, event):
        from .dialogs.about_dialog import AboutDialog

        dialog = AboutDialog()
        dialog.exec_()


class ShowSendFeedbackAction(Action):
    name = Str("Send &Feedback...")
    tooltip = "Send feedback to the development team"

    def perform(self, event):
        from .dialogs.feedback_dialog import SendFeedbackDialog

        dialog = SendFeedbackDialog()
        dialog.exec_()


class OpenGitHubIssuesAction(Action):
    name = Str("Report an &Issue...")
    tooltip = "Open GitHub Issues in your browser"

    def perform(self, event):
        webbrowser.open(GITHUB_ISSUES_URL)


class OpenSciBotsAction(Action):
    name = Str("&Sci-Bots Website")
    tooltip = "Open the Sci-Bots website in your browser"

    def perform(self, event):
        webbrowser.open(SCIBOTS_URL)


class ContactSupportAction(Action):
    """Opens the default mail app with a mailto: link."""
    email = Str()

    def perform(self, event):
        webbrowser.open(f"mailto:{self.email}")


def menu_factory():
    contact_submenu = SMenu(
        ContactSupportAction(
            name="&Technical Support",
            tooltip="Email support@sci-bots.com",
            email="support@sci-bots.com",
        ),
        ContactSupportAction(
            name="&General Inquiries",
            tooltip="Email info@sci-bots.com",
            email="info@sci-bots.com",
        ),
        id="contact_support_submenu",
        name="&Contact Support",
    )

    return SGroup(
        ShowSendFeedbackAction(),
        OpenGitHubIssuesAction(),
        OpenSciBotsAction(),
        contact_submenu,
        AboutMicrodropAction(),
        id="user_help_actions",
    )