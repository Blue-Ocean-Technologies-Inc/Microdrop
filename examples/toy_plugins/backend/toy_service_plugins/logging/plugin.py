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

from .interfaces.i_logging_service import ILoggingService
from .services.logging_service import LoggingService


class LoggingPlugin(Plugin):
    id = 'app.logging.plugin'
    service_offers = List(contributes_to=SERVICE_OFFERS)

    def _service_offers_default(self):
        return [ServiceOffer(protocol=ILoggingService, factory=self._create_service)]

    def _create_service(self):
        return LoggingService()
