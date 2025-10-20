import os
import re
from serial.tools.list_ports import grep

from dropbot.self_test import generate_report, self_test
import dropbot as db

from logger.logger_service import get_logger
logger = get_logger(__name__)


def get_port_name_for_id_to_screen(id_to_screen):
    for port in grep('USB Serial'):
        pattern = re.compile(f".*{id_to_screen}.*")
        teensy = re.search(pattern, port.hwid)
        if bool(teensy):
            return port.device


# List of on-board self-tests.
tests = [{'test_name': 'test_voltage', 'title': 'Test high _voltage'},
         {'test_name': 'test_on_board_feedback_calibration', 'title': 'On-board _feedback calibration'},
         {'test_name': 'test_shorts', 'title': 'Detect shorted channels'},
         {'test_name': 'test_channels', 'title': 'Scan test board'}]

from enum import Enum

class Tests(Enum):
    test_voltage = 'test_voltage'

if __name__ == '__main__':
    proxy = db.SerialProxy(port=get_port_name_for_id_to_screen('VID:PID=16C0:0483'))

    print(proxy.ram_free())

    generate_report(self_test(proxy, tests=[tests[0]["test_name"]]), f".{os.sep}reports{os.sep}report.html", force=True)
