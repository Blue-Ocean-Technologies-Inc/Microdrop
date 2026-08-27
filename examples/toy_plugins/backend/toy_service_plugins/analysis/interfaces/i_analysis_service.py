# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from traits.has_traits import Interface
from traits.trait_types import Str


class IAnalysisService(Interface):

    # task_name
    id = Str

    # define payload
    payload_model = Str

    # response_queue_id

    def process_task(self, task_info):
        """Run analysis on the given data and return the result."""
