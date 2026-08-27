"""Vendored Portable Dropbot driver — the bare minimum the backend
needs: the session API (`session.py`), the serial protocol layer
(`portable_dropbot_service.py`), and the command tables
(`commands.py`).

Vendored verbatim from the private python-driver repository
(gitlab blue-ocean-technologies/dropbot-portable/python-driver,
package commit cf15ac0); the bench tools, generated proxies and
tests were deliberately left behind. To update, re-copy these three
modules from the driver checkout — their internal single-dot
relative imports work unchanged in this location."""
from .session import DropletBotSession

__all__ = ["DropletBotSession"]
