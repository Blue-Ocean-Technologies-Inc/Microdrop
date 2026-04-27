"""Persisted preferences for the SSH / Remote Backend controls.

The two dialogs (SSH Key Portal and Sync Remote Experiments) share a
single preference node — ``microdrop.ssh_controls``. Field values typed
into the dialogs write through to this helper on every keystroke,
which is how ``apptools.preferences`` persists them to ETSConfig.

Defaults are read from ``.env`` the first time the app runs (or
whenever the user hits the "Reset to .env defaults" button in the
Preferences pane).

``password`` is intentionally NOT persisted — it is used only for the
one-time key upload, and plaintext persistence to ETSConfig is a
security concern. It stays on ``SSHControlModel`` (session-only).
"""
import os
import re

from apptools.preferences.api import PreferencesHelper
from dotenv import load_dotenv
from envisage.ui.tasks.api import PreferencesCategory, PreferencesPane
from traits.api import Button, Int, Str, observe
from traitsui.api import Item, VGroup, View

from microdrop_style.text_styles import preferences_group_style_sheet
from microdrop_utils.preferences_UI_helpers import create_item_label_group


# --- .env default constants -------------------------------------------------

_DEFAULT_KEY_NAME = "id_rsa_microdrop"
_DEFAULT_REMOTE_EXPERIMENTS_PATH = "~/Documents/Sci-Bots/Microdrop/Experiments/"
_DEFAULT_SSH_PORT = 22


def _sanitize_host(host: str) -> str:
    """Turn a hostname or IP into a filesystem-safe folder name.

    Replaces dots and colons (including IPv6) with underscores, drops
    anything else that isn't alphanumeric, underscore or hyphen.

    >>> _sanitize_host("192.168.1.10")
    '192_168_1_10'
    >>> _sanitize_host("lab-dropbot.local")
    'lab-dropbot_local'
    >>> _sanitize_host("")
    ''
    """
    if not host:
        return ""
    return re.sub(r"[^A-Za-z0-9_-]", "_", host)


def _env_host() -> str:
    return os.getenv("REMOTE_HOST_IP_ADDRESS", "")


def _env_port() -> int:
    raw = os.getenv("REMOTE_SSH_PORT")
    try:
        return int(raw) if raw else _DEFAULT_SSH_PORT
    except ValueError:
        return _DEFAULT_SSH_PORT


def _env_username() -> str:
    return os.getenv("REMOTE_HOST_USERNAME", "")


class SSHControlPreferences(PreferencesHelper):
    """Persisted configuration for the SSH / Remote Backend dialogs."""

    preferences_path = "microdrop.ssh_controls"

    host                    = Str
    port                    = Int
    username                = Str
    key_name                = Str
    remote_experiments_path = Str
    device_id               = Str

    # --- Defaults (consulted only when no persisted value exists) -----------

    def _host_default(self):
        load_dotenv()
        return _env_host()

    def _port_default(self):
        load_dotenv()
        return _env_port()

    def _username_default(self):
        load_dotenv()
        return _env_username()

    def _key_name_default(self):
        return _DEFAULT_KEY_NAME

    def _remote_experiments_path_default(self):
        return _DEFAULT_REMOTE_EXPERIMENTS_PATH

    def _device_id_default(self):
        return _sanitize_host(self._host_default())

    # --- Auto-derive device_id from host ------------------------------------

    @observe("host")
    def _on_host_changed(self, event):
        """Keep ``device_id`` synced with host unless the user customised it.

        If ``device_id`` is empty or still matches the sanitized form of the
        previous host, repopulate it from the new host. Otherwise leave the
        user's nickname alone.
        """
        old_host = event.old or ""
        old_derived = _sanitize_host(old_host)
        if not self.device_id or self.device_id == old_derived:
            self.device_id = _sanitize_host(self.host)


ssh_controls_tab = PreferencesCategory(
    id="microdrop.ssh_controls.preferences",
    name="SSH / Remote Backend",
)


class SSHControlPreferencesPane(PreferencesPane):
    """Preferences pane contributing the SSH / Remote Backend tab."""

    model_factory = SSHControlPreferences

    category = ssh_controls_tab.id

    settings = VGroup(
        create_item_label_group("host",                    label_text="Host"),
        create_item_label_group("port",                    label_text="SSH Port"),
        create_item_label_group("username",                label_text="Username"),
        create_item_label_group("key_name",                label_text="SSH Key Name"),
        create_item_label_group("remote_experiments_path", label_text="Remote Experiments Path"),
        create_item_label_group("device_id",               label_text="Device ID"),
        label="Remote Backend",
        show_border=True,
        style_sheet=preferences_group_style_sheet,
    )

    view = View(
        Item("_"),
        settings,
        Item("_"),
        Item("_"),
        resizable=True,
    )