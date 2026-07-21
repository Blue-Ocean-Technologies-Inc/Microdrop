import webbrowser

from pyface.action.api import Action
from pyface.tasks.action.api import SGroup, SMenu
from traits.api import Any, Int, Str

from .consts import (
    ARCHITECTURE_HTML_PATH,
    FEEDBACK_URL,
    GITHUB_ISSUES_URL,
    MICRODROP_LAUNCHER_README_URL,
    SCIBOTS_URL,
    SUPPORT_EMAIL,
    INFO_EMAIL,
)

from microdrop_application.dialogs.consts import (
    DEFAULT_WEB_VIEW_DIALOG_WIDTH,
    DEFAULT_WEB_VIEW_DIALOG_HEIGHT,
)


class OpenWebViewDialogAction(Action):
    """Opens a WebViewDialog rendering ``source`` (URL string or local Path)."""

    source = Any()
    window_title = Str()
    width = Int(DEFAULT_WEB_VIEW_DIALOG_WIDTH)
    height = Int(DEFAULT_WEB_VIEW_DIALOG_HEIGHT)
    dialog = Any()

    def perform(self, event):
        # Imported lazily so QtWebEngine only initializes on first use.
        from microdrop_application.dialogs.web_view_dialog import WebViewDialog

        self.dialog = WebViewDialog(self.source, self.window_title,
                                    width=self.width, height=self.height)
        self.dialog.show()


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
            tooltip=f"Email {SUPPORT_EMAIL}",
            email=SUPPORT_EMAIL,
        ),
        ContactSupportAction(
            name="&General Inquiries",
            tooltip=f"Email {INFO_EMAIL}",
            email=INFO_EMAIL,
        ),
        id="contact_support_submenu",
        name="&Contact Support",
    )

    return SGroup(
        OpenWebViewDialogAction(
            name="Send &Feedback...",
            tooltip="Send feedback to the development team",
            source=FEEDBACK_URL,
            window_title="Send Feedback",
            width=600,
            height=700,
        ),
        OpenGitHubIssuesAction(),
        OpenSciBotsAction(),
        OpenWebViewDialogAction(
            name="&Download MicroDrop Launcher...",
            tooltip="View the MicroDrop Launcher README with download instructions",
            source=MICRODROP_LAUNCHER_README_URL,
            window_title="Download MicroDrop Launcher",
        ),
        contact_submenu,
        OpenWebViewDialogAction(
            name="&About MicroDrop...",
            tooltip="Learn about MicroDrop's architecture and capabilities",
            source=ARCHITECTURE_HTML_PATH,
            window_title="About MicroDrop",
        ),
        id="user_help_actions",
    )