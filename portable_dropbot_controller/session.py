# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The session object the backend mixins hold as ``self.proxy``.

The ``dropbot_portable`` package's ``DropBotSession`` exposes the raw
transport as ``uart``; the generated per-board proxies are the typed API
the driver is converging on, the way ``dropbot.SerialProxy`` is for the
classic DropBot. This subclass puts both boards' proxies on the session so
new backend code is written against that API, while the legacy ``uart``
calls migrate as they are touched.

Import from the package root, never its submodules: the package puts its
own directory on ``sys.path`` for flat intra-package imports, so
``dropbot_portable.session`` is a second copy of the module the root
exports, with distinct classes.
"""

# Third-party imports.
from dropbot_portable import DropBotSession, MotorBoardProxy, SignalBoardProxy


class PortableDropbotSession(DropBotSession):
    """``DropBotSession`` plus the generated board proxies.

    The proxies wrap the same transport, so they share its connection state
    and reply matching; a call on a board that is not logged in simply times
    out like any other unanswered command.
    """

    def __init__(self, port=None, baudrate=115200):
        super().__init__(port=port, baudrate=baudrate)
        #: Typed proxy for the signal board (HV, capacitance, temperature,
        #: lighting, PMT).
        self.sig = SignalBoardProxy(self._uart)
        #: Typed proxy for the motor board (tray, magnet, pogos, filter
        #: wheel, PMT motor).
        self.motor = MotorBoardProxy(self._uart)
