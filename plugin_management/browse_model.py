"""Qt-free model for the Browse Plugins window.

Lists the packages available in the remote plugin channel (one row per
package), formats a package's full metadata for the details panel, and
delegates fetch/install to ``package_installer``. No Qt, no dialogs, no
threading — the controller (a Handler) owns those.
"""
import re
from datetime import datetime, timezone

from traits.api import Dict, HasTraits, Instance, List, Str, Bool, observe

from plugin_management import package_installer
from plugin_management.consts import PLUGIN_CHANNEL_URL
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _format_size(size) -> str:
    """Bytes -> binary KiB string (matching pixi), or '' if unknown."""
    if size is None:
        return ""
    return f"{size / 1024:.2f} KiB"


def _format_timestamp(ms) -> str:
    """Milliseconds since epoch -> 'YYYY-MM-DD HH:MM:SS UTC', or '' if unknown."""
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC")


def _version_key(version: str) -> tuple:
    """Sort key for version strings: tuple of leading integers per dotted part."""
    parts = []
    for part in str(version).split("."):
        m = re.match(r"\d+", part)
        parts.append(int(m.group()) if m else 0)
    return tuple(parts)


def format_details(raw: dict) -> str:
    """Render a package's full metadata as the plain-text details block."""
    fn = raw.get("fn", "") or ""
    header = fn[:-len(".conda")] if fn.endswith(".conda") else raw.get("name", "")
    rows = [
        ("Name", raw.get("name", "")),
        ("Version", str(raw.get("version", ""))),
        ("Build", raw.get("build", "")),
        ("Size", _format_size(raw.get("size"))),
        ("Timestamp", _format_timestamp(raw.get("timestamp"))),
        ("Subdir", raw.get("subdir", "")),
        ("NoArch", raw.get("noarch", "") or ""),
        ("File Name", fn),
        ("URL", raw.get("url", "")),
        ("MD5", raw.get("md5", "")),
        ("SHA256", raw.get("sha256", "")),
    ]
    lines = [header, "-" * max(len(header), 33), ""]
    lines += [f"{label:<19} {value}" for label, value in rows]
    depends = raw.get("depends") or []
    if depends:
        lines += ["", "Dependencies:"] + [f" - {d}" for d in depends]
    return "\n".join(lines)


class AvailablePackage(HasTraits):
    """One package available in the channel: name/version + its full metadata."""
    name = Str()
    version = Str()
    raw = Dict()


class BrowsePluginsModel(HasTraits):
    """The packages available in the remote channel + fetch/install operations."""

    channel_url = Str(PLUGIN_CHANNEL_URL)
    packages = List(Instance(AvailablePackage))
    selected = Instance(AvailablePackage)
    details_text = Str()
    stale = Bool(False)

    def fetch_data(self):
        """Worker-thread safe: return (packages, stale). Does NOT touch traits.
        Tries the channel; on failure falls back to the app-data cache."""
        try:
            return package_installer.search_channel(self.channel_url), False
        except package_installer.InstallError as e:
            logger.warning(f"channel search failed, using cached list: {e}")
            return package_installer.read_cached_index(), True

    @observe("selected")
    def _update_details(self, event):
        """Auto-fill the details panel for the selected row (selection happens
        on the GUI thread). Blank when nothing is selected."""
        self.details_text = format_details(self.selected.raw) if self.selected else ""

    def set_packages(self, data, stale):
        """GUI thread: build one row per package (latest version) + flags."""
        self.stale = stale
        self.packages = self._rows_from(data)

    def _rows_from(self, data):
        latest = {}
        for pkg in data:
            name = pkg.get("name")
            if not name:
                continue
            current = latest.get(name)
            if current is None or _version_key(pkg.get("version", "")) >= _version_key(
                    current.get("version", "")):
                latest[name] = pkg
        return [AvailablePackage(name=p["name"], version=str(p.get("version", "")),
                                 raw=p)
                for p in sorted(latest.values(), key=lambda p: p["name"])]

    def do_install(self, name):
        """Worker-thread safe: install via package_installer (no trait mutation)."""
        return package_installer.install_from_channel(name, self.channel_url)
