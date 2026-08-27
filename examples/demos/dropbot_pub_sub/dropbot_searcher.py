# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from serial.tools.list_ports import grep
from logger.logger_service import get_logger
import re

logger = get_logger(__name__)


def check_connected_ports_hwid(id_to_screen, regexp='USB Serial'):
    """
    Check connected USB ports for a specific hardware id.
    """

    connected_ports = grep(regexp)
    valid_ports = []

    for port in connected_ports:
        pattern = re.compile(f".*{id_to_screen}.*")
        teensy = re.search(pattern, port.hwid)
        if bool(teensy):
            valid_ports.append(port)

    return valid_ports


def check_dropbot_devices_available(hwids_to_check):
    """
    Method to find the USB port of the DropBot if it is connected.
    """

    for hwid in hwids_to_check:
        valid_ports = check_connected_ports_hwid(hwid)
        if len(valid_ports) > 0:
            port_name = str(valid_ports[0].device)
            # Indicate success by returning the port name
            logger.info(f'DropBot found on port {port_name}, topic is dropbot/info')
            return port_name

        else:
            raise Exception('DropBot not found')


if __name__ == "__main__":
    hwids = ['VID:PID=16C0:0483']
    check_dropbot_devices_available(hwids)
