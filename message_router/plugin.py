from envisage.api import Plugin, ExtensionPoint
from traits.api import List, Str, Dict, Instance, observe, on_trait_change
import dramatiq
import uuid

from .consts import ACTOR_TOPIC_ROUTES, PKG, PKG_name
from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterActor

# Initialize logger
logger = get_logger(__name__)
# remove prometheus metrics for now
from microdrop_utils.broker_server_helpers import remove_middleware_from_dramatiq_broker
remove_middleware_from_dramatiq_broker(middleware_name="dramatiq.middleware.prometheus", broker=dramatiq.get_broker())


class MessageRouterPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'
    router_actor = Instance(MessageRouterActor)
    listener_queue = "_" + str(uuid.uuid4())  # queue names cannot start with number, has to be letter on underscore.

    # This tells us that the plugin offers the 'greetings' extension point,
    # and that plugins that want to contribute to it must each provide a list
    # of strings (Str).
    actor_topic_routing = ExtensionPoint(
        List(Dict(Str, List)), id=ACTOR_TOPIC_ROUTES,

        desc='actor topic routing information: keys should be different actors. And values for each are a list of '
             'topics that it acts upon'
    )

    def _router_actor_default(self):
        """ Trait initializer for pubsub actor"""
        return MessageRouterActor(listener_queue=self.listener_queue)

    def start(self):
        # Wire the registry's extension-point listeners to this plugin's
        # traits so the handlers below fire when contributions change at
        # runtime. Opt-in (envisage never calls it for you), and only
        # possible here: the registry is reachable once the plugin is
        # attached to the application, not at construction.
        self.connect_extension_point_traits()

        # assign topics to actors when plugin starts
        for actor_topics_routes in self.actor_topic_routing:
            # add subscribers to topics
            for actor_name, topics_list in actor_topics_routes.items():
                for topic in topics_list:
                    self.router_actor.message_router_data.add_subscriber_to_topic(topic, actor_name)

    @on_trait_change("actor_topic_routing_items")
    def _on_actor_topic_routing_items_changed(self, event):
        """A contribution changed while the app is running.

        Plugin-driven changes (a contributing plugin mutating OR
        reassigning its contribution trait, plugins added/removed from
        the manager) always carry an index, which ExtensionPoint.connect
        surfaces as this synthetic "<name>_items" property event. No
        real ``actor_topic_routing_items`` trait exists, so the
        string-matched on_trait_change must bind it — observe() rejects
        unknown names. ``event`` is the ExtensionPointChangedEvent.
        """
        logger.info(f"actor topic routing changed: added={event.added}, "
                    f"removed={event.removed}, index={event.index}")

    @observe("actor_topic_routing")
    def _on_actor_topic_routing_changed(self, event):
        """Index-less wholesale replacement of the extension point
        (registry.set_extensions) — never fired for plugin contribution
        changes; covered for completeness."""
        logger.info(f"actor topic routing replaced: removed={event.old}, "
                    f"added={event.new}")
