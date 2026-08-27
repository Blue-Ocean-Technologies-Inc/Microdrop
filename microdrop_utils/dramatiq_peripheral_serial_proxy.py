# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import time

from .dramatiq_pub_sub_helpers import publish_message
from mr_box_peripheral_board.proxy import SerialProxy, BOARD_BAUDRATE
from peripheral_controller.consts import DISCONNECTED, CONNECTED
import base_node_rpc as bnr
import functools as ft

from logger.logger_service import get_logger
logger = get_logger(__name__)

######## Same as DramatiqDropbotSerialPRoxy ###################

class DramatiqPeripheralSerialProxy(SerialProxy):

    def connect(self, port=None, baudrate=BOARD_BAUDRATE, settling_time_s=1):
        # If the monitor is already running, terminate it
        if self.monitor is not None:
            self.terminate()
            self.monitor = None

        monitor = bnr.ser_async.BaseNodeSerialMonitor(port=port, baudrate=baudrate)

        # define the dramatiq pub sub wrappers
        def connected_wrapper(f, *args, **kwargs):
            publish_message(f'connected', CONNECTED)
            f(*args, **kwargs)


        def disconnected_wrapper(f, *args, **kwargs):
            publish_message(f'disconnected', DISCONNECTED)
            f(*args, **kwargs)


        monitor.disconnected_event.set = ft.partial(disconnected_wrapper,monitor.disconnected_event.set)
        monitor.connected_event.set = ft.partial(connected_wrapper, monitor.connected_event.set)

        monitor.start()
        monitor.connected_event.wait()

        time.sleep(settling_time_s)

        self.monitor = monitor
        return self.monitor
