# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from traits.api import Interface, Str, Any


class IPeripheralDeviceControlMixinService(Interface):
    """Generic interface for a peripheral-device control mixin.

    Concrete devices (z-stage magnet, heater, ...) subclass this with a
    narrowed ``proxy`` type and their own device-specific exposed methods. Each
    device must use its OWN subclass as the service protocol so the plugin only
    composes the mixins belonging to that device.
    """

    id = Str
    name = Str
    proxy = Any

    ################################### Exposed Methods ###############################

    def on_topic_request(self, message):
        """A method called when a device topic request is received. Methods to be
        exposed follow the ``on_<specific_sub_topic>_request`` naming convention.
        """
        pass
