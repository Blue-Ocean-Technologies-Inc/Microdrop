"""Qt-free model for the Browse Plugins window.

Lists the packages available in the remote plugin channel (one row per
package), formats a package's full metadata for the details panel, and
delegates fetch/install to ``package_installer``. No Qt, no dialogs, no
threading — the controller (a Handler) owns those.
"""
import html
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


# CSS for the details panel. Colors adapt to the OS light/dark scheme via
# prefers-color-scheme (QWebEngine follows it) so the panel matches the themed
# app without the model needing any Qt dependency.
_DETAILS_CSS = """
  body { font-family: "Segoe UI", system-ui, sans-serif; font-size: 12px; margin: 8px; }
  h2 { font-size: 14px; margin: 0 0 10px; word-break: break-all; }
  h3 { font-size: 12px; margin: 14px 0 4px; }
  table { border-collapse: collapse; width: 100%; }
  th { text-align: left; vertical-align: top; padding: 2px 12px 2px 0;
       font-weight: 600; white-space: nowrap; }
  td { vertical-align: top; padding: 2px 0; word-break: break-all;
       font-family: Consolas, "Courier New", monospace; }
  ul.deps { margin: 4px 0; padding-left: 18px; }
  ul.deps li { font-family: Consolas, "Courier New", monospace; }
  body { color: #202020; background: #ffffff; }
  th { color: #555; } a { color: #0a58ca; }
  @media (prefers-color-scheme: dark) {
    body { color: #e0e0e0; background: #2b2b2b; }
    th { color: #9aa7b0; } a { color: #6cb6ff; }
  }
"""


def format_details_html(raw: dict) -> str:
    """Render a package's full metadata as a styled HTML details document.

    The URL is a real ``<a href>`` (the HTMLEditor opens it in the system
    browser); long values (hashes, URL) wrap. Every value is HTML-escaped."""
    def esc(value):
        return html.escape(str(value if value is not None else ""))

    fn = raw.get("fn", "") or ""
    header = fn[:-len(".conda")] if fn.endswith(".conda") else (raw.get("name", "") or "")
    url = raw.get("url", "") or ""
    url_html = f'<a href="{esc(url)}">{esc(url)}</a>' if url else ""
    rows = [
        ("Name", esc(raw.get("name", ""))),
        ("Version", esc(raw.get("version", ""))),
        ("Build", esc(raw.get("build", ""))),
        ("Size", esc(_format_size(raw.get("size")))),
        ("Timestamp", esc(_format_timestamp(raw.get("timestamp")))),
        ("Subdir", esc(raw.get("subdir", ""))),
        ("NoArch", esc(raw.get("noarch", "") or "")),
        ("File Name", esc(fn)),
        ("URL", url_html),
        ("MD5", esc(raw.get("md5", ""))),
        ("SHA256", esc(raw.get("sha256", ""))),
    ]
    row_html = "".join(f"<tr><th>{label}</th><td>{value}</td></tr>"
                       for label, value in rows)
    depends = raw.get("depends") or []
    deps_html = ""
    if depends:
        items = "".join(f"<li>{esc(d)}</li>" for d in depends)
        deps_html = f"<h3>Dependencies</h3><ul class='deps'>{items}</ul>"
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<style>{_DETAILS_CSS}</style></head><body>"
            f"<h2>{esc(header)}</h2><table>{row_html}</table>{deps_html}"
            f"</body></html>")


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
        self.details_text = format_details_html(self.selected.raw) if self.selected else ""

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
