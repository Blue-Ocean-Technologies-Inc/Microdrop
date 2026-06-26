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
