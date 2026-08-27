# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from envisage.api import Plugin, SERVICE_OFFERS
from envisage.service_offer import ServiceOffer
from traits.trait_types import List

from .interfaces.i_analysis_service import IAnalysisService
from .services.analysis_service import AnalysisService
from .services.dramatiq_analysis_service import DramatiqAnalysisService


class AnalysisPlugin(Plugin):
    id = 'app.analysis.plugin'
    service_offers = List(contributes_to=SERVICE_OFFERS)

    def _service_offers_default(self):
        """Return the service offers."""
        return [
            ServiceOffer(protocol=IAnalysisService, factory=self._create_service, properties={"type": "regular"}),
            ServiceOffer(protocol=IAnalysisService, factory=self._create_service_dramatiq,

                         properties={
                             "type": "dramatiq",
                             "id": "dramatiq_analysis_service",

                         }),
        ]

    def _create_service(self, *args, **kwargs):
        """Create an analysis service."""

        # TODO: while this creation happens, automatically we get the kwargs as the properties defined in the service
        # offer. We have to exploit this somehow. Its a useful behavious potentially
        return AnalysisService(id="analysis_service", payload_model='')

    def _create_service_dramatiq(self, id, *args, **kwargs):
        """Create an analysis service."""

        return DramatiqAnalysisService(id=id)
