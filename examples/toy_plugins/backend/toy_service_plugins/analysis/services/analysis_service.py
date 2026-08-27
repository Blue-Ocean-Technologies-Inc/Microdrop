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

from traits.has_traits import provides, HasTraits
from traits.trait_types import Str

from ..interfaces.i_analysis_service import IAnalysisService


@provides(IAnalysisService)
class AnalysisService(HasTraits):

    # task_name
    id = Str

    # define payload
    payload_model = Str('{"args_to_sum": []}')

    @staticmethod
    def process_task(task_info):
        print(f"Received task: {task_info}, processing in backend...")
        parameters = task_info['args_to_sum']
        time.sleep(task_info["sleep_time"])
        result = sum(parameters)
        print("Analysis result:", result)
        return result
