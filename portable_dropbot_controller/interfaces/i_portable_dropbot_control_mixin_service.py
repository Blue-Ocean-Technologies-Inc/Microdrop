from traits.api import Interface, Str


class IPortableDropbotControlMixinService(Interface):
    """
    Interface for Portable Dropbot mixin services exposing topic-based
    request handlers.
    """

    id = Str
    name = Str

    def on_topic_request(self, message):
        """
        Naming convention for exposed methods:
        `on_<topic-name>_request(message)`.
        """
        pass
