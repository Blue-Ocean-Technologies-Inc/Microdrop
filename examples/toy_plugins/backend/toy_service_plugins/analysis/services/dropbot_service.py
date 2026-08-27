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

import dramatiq
from traits.has_traits import provides, HasTraits
from traits.trait_types import Str
from dramatiq import get_broker

from ..interfaces.i_dropbot_service import IDropbotService

from logger.logger_service import get_logger

logger = get_logger(__name__)
broker = get_broker()

@provides(IDropbotService)
class DramatiqAnalysisService(HasTraits):

    # task_name
    id = Str

    # define payload
    payload_model = Str('{"voltage": Float, "frequency": Float}')

    @dramatiq.actor
    def process_task(task_info):

        print(f"Received task: {task_info}, processing in backend...")

        # get args from task_info
        voltage = task_info.get("voltage", 0)
        frequency = task_info.get("frequency", 0)

        time.sleep(2)

        logger.info(f"Changed the Voltage -- Voltage = {voltage}, Frequency = {frequency}")

