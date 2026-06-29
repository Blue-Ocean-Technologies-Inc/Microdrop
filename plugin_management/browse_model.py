"""Qt-free model for the Browse Plugins window.

Lists the packages available in the remote plugin channel (one row per
package), formats a package's full metadata for the details panel, and
delegates fetch/install to ``package_installer``. No Qt, no dialogs, no
threading — the controller (a Handler) owns those.
"""
import re
from datetime import datetime, timezone

from traits.api import Dict, HasTraits, Instance, List, Str, Bool

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
