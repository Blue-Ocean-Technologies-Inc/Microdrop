from traits.api import Interface, Str


class IOpenDropControlMixinService(Interface):
    """
    Interface for OpenDrop mixin services that expose topic-based request handlers.
    """

    id = Str
    name = Str

    def on_topic_request(self, message):
        """
        Naming convention for exposed methods:
        `on_<topic-name>_request(message)`.
        """
        pass
