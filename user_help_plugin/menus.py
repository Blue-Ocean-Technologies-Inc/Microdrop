import webbrowser

from pyface.action.api import Action
from pyface.tasks.action.api import SGroup, SMenu
from traits.api import Any, Bool, Int, Str

from logger.logger_service import get_logger

logger = get_logger(__name__)

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
    open_links_externally = Bool(False)
    dialog = Any()

    def perform(self, event):
        # Imported lazily so QtWebEngine only initializes on first use.
        from microdrop_application.dialogs.web_view_dialog import WebViewDialog

        self.dialog = WebViewDialog(self.source, self.window_title,
                                    width=self.width, height=self.height,
                                    open_links_externally=self.open_links_externally)
        self.dialog.show()


class OpenGithubMarkdownDialogAction(OpenWebViewDialogAction):
    """Renders a GitHub markdown file (just the document, not the full GitHub
    page) in a WebViewDialog; falls back to loading the GitHub page itself if
    fetching or rendering fails."""

    open_links_externally = Bool(True)

    def perform(self, event):
        # Imported lazily so QtWebEngine only initializes on first use.
        from microdrop_application.dialogs.web_view_dialog import WebViewDialog
        from microdrop_utils.markdown_helpers import fetch_github_markdown_as_html

        try:
            html_content = fetch_github_markdown_as_html(self.source)
        except Exception as e:
            logger.warning(f"Failed to render markdown from {self.source}: {e}. "
                           f"Falling back to loading the page directly.")
            return super().perform(event)

        self.dialog = WebViewDialog(html_content=html_content, title=self.window_title,
                                    width=self.width, height=self.height,
                                    open_links_externally=self.open_links_externally)
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
        contact_submenu,
        OpenWebViewDialogAction(
            name="&About MicroDrop...",
            tooltip="Learn about MicroDrop's architecture and capabilities",
            source=ARCHITECTURE_HTML_PATH,
            window_title="About MicroDrop",
        ),
        id="user_help_actions",
    )


def launcher_menu_factory():
    """Separate bottom group so the launcher item sits below a separator line."""
    return SGroup(
        OpenGithubMarkdownDialogAction(
            name="&Download MicroDrop Launcher...",
            tooltip="View the MicroDrop Launcher README with download instructions",
            source=MICRODROP_LAUNCHER_README_URL,
            window_title="Download MicroDrop Launcher",
        ),
        id="microdrop_launcher_actions",
    )