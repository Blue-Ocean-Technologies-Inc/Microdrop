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
        self._update_router_subscriptions(added=self.actor_topic_routing,
                                          removed=[])

    def _update_router_subscriptions(self, added, removed):
        """Apply contribution deltas to the router's topic->subscriber map.

        Removals run first so a wholesale reassignment (old list removed,
        new list added in one event) keeps any (actor, topic) pair common
        to both — the other order would strip the freshly re-added pair.
        """
        data = self.router_actor.message_router_data
        for actor_topics_routes in removed:
            for actor_name, topics_list in actor_topics_routes.items():
                for topic in topics_list:
                    try:
                        data.remove_subscriber_from_topic(topic, actor_name)
                        logger.info(f"router unsubscribed {actor_name} from {topic}")
                    except (KeyError, ValueError):
                        # Two contributions can declare the same (actor,
                        # topic) pair; the flat map holds it once, so the
                        # second removal finds nothing. Not an error.
                        logger.warning(f"router unsubscribe skipped: "
                                       f"{actor_name} not subscribed to {topic}")
        for actor_topics_routes in added:
            for actor_name, topics_list in actor_topics_routes.items():
                for topic in topics_list:
                    data.add_subscriber_to_topic(topic, actor_name)
                    logger.info(f"router subscribed {actor_name} to {topic}")

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
        self._update_router_subscriptions(event.added, event.removed)

    @observe("actor_topic_routing")
    def _on_actor_topic_routing_changed(self, event):
        """Index-less wholesale replacement of the extension point
        (registry.set_extensions) — never fired for plugin contribution
        changes; covered for completeness. The connect listener delivers
        removed contributions as ``event.old`` and added as ``event.new``.
        """
        logger.info(f"actor topic routing replaced: removed={event.old}, "
                    f"added={event.new}")
        self._update_router_subscriptions(added=event.new, removed=event.old)
