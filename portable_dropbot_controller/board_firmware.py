# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The boards' firmware versions as the driver judges them:
``DropBotSession.check_versions`` reads each board's tag and compares it
with the bindings' minimum (``proxy.MCU_MIN_COMPATIBLE_FW`` /
``DRV_MIN_COMPATIBLE_FW``). This module only turns that verdict into the
version tuples the backend gates features on and the payload the status
pane shows, and ``BoardFirmwareMixin`` holds them per connection for the
monitor mixin. No Qt: unit-testable without hardware."""

# Standard library imports.
import time

# Third-party imports.
from dropbot_portable.flash_firmware import parse_version

# Enthought library imports.
from traits.api import Dict, HasTraits

# Local imports.
from .consts import FIRMWARE_READ_RETRY_DELAY_S, firmware_versions_publisher

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: check_versions board names -> board_firmware_versions keys and the labels
#: the outdated-firmware warning uses.
FIRMWARE_BOARDS = (("signal", "mcu", "MCU"), ("motor", "motor", "Motor"))


def summarize_firmware_checks(checks):
    """Turn ``check_versions`` output ({board: (running, expected, match)})
    into the version tuples per board ("mcu" / "motor"; unknown boards
    left out) and the FirmwareVersionsUpdated payload."""
    versions, tags, outdated = {}, {}, []

    for board, key, label in FIRMWARE_BOARDS:
        running, expected, match = checks.get(board, (None, None, None))

        # The vendor's shared tag parser: "DroSIG_1.0.1.31" -> (1, 0, 1, 31);
        # None for "unknown" (no VERSION reply).
        numbers = parse_version(str(running)) if running else None

        if numbers:
            versions[key] = numbers
            tags[key] = str(running)

        if match is False:
            outdated.append(f"{label} board firmware {running} (needs {expected})")

    payload = {
        "mcu": tags.get("mcu", ""),
        "motor": tags.get("motor", ""),
        "outdated": outdated,
    }

    return versions, payload


def firmware_at_least(versions, board, version_tuple):
    """Whether ``board``'s running firmware in ``versions`` is
    ``version_tuple`` or newer; False while it is unknown."""
    running = versions.get(board)

    return bool(running) and tuple(running) >= tuple(version_tuple)


class BoardFirmwareMixin(HasTraits):
    """The boards' firmware versions of the live connection, and the gates
    on them. Composes into the controller, which provides ``proxy`` and
    ``_proxy_call``."""

    #: Running firmware per board, read on connect: "mcu" / "motor" ->
    #: int tuple, e.g. (1, 0, 1, 31). A board missing is unknown.
    board_firmware_versions = Dict()

    def _read_board_firmware(self, session, attempts=2):
        """Read both boards' firmware the vendor's way
        (``DropBotSession.check_versions``, which judges each against the
        driver bindings' minimum) into board_firmware_versions, and answer
        the FirmwareVersionsUpdated payload. MicroDrop never flashes: an
        outdated board is only reported.

        A failed read, or a board answering no version, is retried after
        FIRMWARE_READ_RETRY_DELAY_S: a board still busy with its boot
        homing answers late."""

        for attempt in range(attempts):
            if attempt:
                time.sleep(FIRMWARE_READ_RETRY_DELAY_S)

            try:
                checks = session.check_versions(ignore=True)
            except Exception as exc:
                logger.warning(f"Portable Dropbot firmware version read failed: {exc}")
                checks = {}

            # match None is check_versions' "unknown": no VERSION reply.
            if checks and all(match is not None for *_, match in checks.values()):
                break

        self.board_firmware_versions, firmware = summarize_firmware_checks(checks)
        logger.info(f"Portable Dropbot firmware: {firmware}")

        return firmware

    def _mcu_firmware_at_least(self, version_tuple):
        """Whether the signal board (MCU) runs ``version_tuple`` or newer;
        False while unknown."""
        return firmware_at_least(self.board_firmware_versions, "mcu", version_tuple)

    def _motor_firmware_at_least(self, version_tuple):
        """Whether the motor board runs ``version_tuple`` or newer; False
        while unknown."""
        return firmware_at_least(self.board_firmware_versions, "motor", version_tuple)

    def _motor_firmware_known(self):
        """Whether the motor board's firmware version is known, reading the
        versions again first while it is not: what is gated on it must not
        guess."""

        if "motor" not in self.board_firmware_versions and self.proxy is not None:
            ok, firmware = self._proxy_call(
                "firmware version read",
                lambda: self._read_board_firmware(self.proxy, attempts=1),
            )

            if ok:
                firmware_versions_publisher.publish(firmware)

        return "motor" in self.board_firmware_versions
