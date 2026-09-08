"""Vendored Portable Dropbot driver.

Copied from the private python-driver repository
(gitlab blue-ocean-technologies/dropbot-portable/python-driver), branch
``main`` at commit 41ea710 (2026-09-08):

    session.py                  high-level session API (DropletBotSession)
    portable_dropbot_service.py serial transport + command helpers (DropletBotUart)
    commands.py                 hand-maintained command tables + alarm decoding
    commands_generated.py       command ids / handler map generated from firmware
    proxy.py                    typed per-board proxies generated from firmware

The bench tools, the test-suite UI and the tests were deliberately left
behind. There are NO Microdrop-local patches in this package: a change the
backend needs goes to the driver repository first and lands here on the
next re-vendor, which is a plain copy of the five modules above (their
single-dot relative imports work unchanged in this location). The only
local difference is the import prologue, which the repo's import-section
stamper hook labels on commit; the code is untouched. Microdrop-specific
glue lives one level up (``portable_dropbot_controller/session.py``).
"""

# Local imports.
from .proxy import MotorBoardProxy, SignalBoardProxy
from .session import DropletBotSession

__all__ = ["DropletBotSession", "MotorBoardProxy", "SignalBoardProxy"]
