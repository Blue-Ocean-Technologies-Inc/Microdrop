"""Persist the user's protocol-tree column visibility across app restarts.

The protocol-tree header right-click menu
(``ProtocolTreeWidget._on_header_context_menu``) lets the user toggle which
columns are shown. Without persistence those choices reset on every launch.
We store a small JSON map ``{col_name: visible}`` under the per-user app
config directory (``ETSConfig.application_home`` — the same root the rest of
the app uses) so the same columns reappear next time.

Keyed by ``col_name`` (the stable display identity from the column model),
not by column index: indices shift whenever the column set changes, names
don't. A column missing from the saved map falls back to its
``hidden_by_default`` flag, so newly added columns still honour their own
default rather than being forced visible.

All filesystem access is best-effort: a missing/unreadable/unwritable
settings file degrades to "no persisted preference" and is logged, never
raised — column visibility must never crash the tree.
"""

import json
from pathlib import Path

from traits.etsconfig.api import ETSConfig

from logger.logger_service import get_logger

logger = get_logger(__name__)

_SETTINGS_FILENAME = "protocol_tree_column_visibility.json"


def _settings_path() -> Path:
    return Path(ETSConfig.application_home) / _SETTINGS_FILENAME


def load_column_visibility() -> dict[str, bool]:
    """Return the persisted ``{col_name: visible}`` map.

    Returns an empty dict when no settings file exists yet or it cannot be
    read/parsed — callers treat an absent entry as "use the column default".
    """
    path = _settings_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning(f"Could not read column visibility settings {path}: {exc}")
        return {}

    if not isinstance(data, dict):
        logger.warning(f"Ignoring malformed column visibility settings {path}")
        return {}
    return {str(name): bool(visible) for name, visible in data.items()}


def save_column_visibility(visibility: dict[str, bool]) -> None:
    """Persist the ``{col_name: visible}`` map, creating the config dir if needed."""
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {str(name): bool(visible) for name, visible in visibility.items()},
                f,
                indent=2,
            )
    except OSError as exc:
        logger.warning(f"Could not write column visibility settings {path}: {exc}")
