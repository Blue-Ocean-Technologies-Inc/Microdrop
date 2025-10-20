from envisage.api import Plugin, ExtensionPoint
from traits.api import List, Str, Dict, Instance
import dramatiq
import uuid

from .consts import ACTOR_TOPIC_ROUTES, PKG, PKG_name
from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterActor

# Initialize logger
logger = get_logger(__name__)
# remove prometheus metrics for now
for el in dramatiq.get_broker().middleware:
    if el.__module__ == "dramatiq.middleware.prometheus":
        dramatiq.get_broker().middleware.remove(el)


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
        # assign topics to actors when plugin starts

        for actor_topics_routes in self.actor_topic_routing:
            # add subscribers to topics
            for actor_name, topics_list in actor_topics_routes.items():
                for topic in topics_list:
                    self.router_actor.message_router_data.add_subscriber_to_topic(topic, actor_name)
