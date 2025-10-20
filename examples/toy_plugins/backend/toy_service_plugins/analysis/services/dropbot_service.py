import time

import dramatiq
from traits.has_traits import provides, HasTraits
from traits.trait_types import Str
from dramatiq import get_broker

from ..interfaces.i_dropbot_service import IDropbotService

from microdrop_utils._logger import get_logger

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

