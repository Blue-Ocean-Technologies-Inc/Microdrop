from traits.api import HasTraits, Dict, Str, Instance
import dramatiq

from microdrop_utils.dramatiq_controller_base import DramatiqControllerBase
from microdrop_utils.redis_manager import RedisHashDictProxy

from logger.logger_service import get_logger
from microdrop_utils.timestamped_message import TimestampedMessage

logger = get_logger(__name__)

DEFAULT_STORAGE_KEY_NAME = "microdrop:message_router_data"


def publish_message(message: str, topic: str, actor_to_send: str = "message_router_actor", queue_name: str = "default", 
                    message_kwargs=None, message_options=None):
    """
    Publish a message to a given actor with a certain topic
    """
    logger.debug(f"Publishing message: {message} to actor: {actor_to_send} on topic: {topic}")

    broker = dramatiq.get_broker()

    if message_options is None:
        message_options = {"max_retries": 1}

    if message_kwargs is None:
        message_kwargs = {}

    message = dramatiq.Message(
        queue_name=queue_name,
        actor_name=actor_to_send,
        args=(message, topic),
        kwargs=message_kwargs,
        options=message_options,
    )

    broker.enqueue(message)


class MQTTMatcher:
    """Intended to manage topic filters including wildcards.

    Internally, MQTTMatcher use a prefix tree (trie) to store
    values associated with filters, and has an iter_match()
    method to iterate efficiently over all filters that match
    some topic name.

    This was taken from https://github.com/eclipse/paho.mqtt.python/blob/master/src/paho/mqtt/matcher.py

    """

    class Node:
        __slots__ = '_children', '_content'

        def __init__(self):
            self._children = {}
            self._content = None

    def __init__(self):
        self._root = self.Node()

    def __setitem__(self, key, value):
        """Add a topic filter :key to the prefix tree
        and associate it to :value"""
        node = self._root
        for sym in key.split('/'):
            node = node._children.setdefault(sym, self.Node())
        node._content = value

    def __getitem__(self, key):
        """Retrieve the value associated with some topic filter :key"""
        try:
            node = self._root
            for sym in key.split('/'):
                node = node._children[sym]
            if node._content is None:
                raise KeyError(key)
            return node._content
        except KeyError as ke:
            raise KeyError(key) from ke

    def __delitem__(self, key):
        """Delete the value associated with some topic filter :key"""
        lst = []
        try:
            parent, node = None, self._root
            for k in key.split('/'):
                parent, node = node, node._children[k]
                lst.append((parent, k, node))
            # TODO
            node._content = None
        except KeyError as ke:
            raise KeyError(key) from ke
        else:  # cleanup
            for parent, k, node in reversed(lst):
                if node._children or node._content is not None:
                    break
                del parent._children[k]

    def iter_match(self, topic):
        """Return an iterator on all values associated with filters
        that match the :topic"""
        lst = topic.split('/')
        normal = not topic.startswith('$')

        def rec(node, i=0):
            if i == len(lst):
                if node._content is not None:
                    yield node._content
            else:
                part = lst[i]
                if part in node._children:
                    for content in rec(node._children[part], i + 1):
                        yield content
                if '+' in node._children and (normal or i > 0):
                    for content in rec(node._children['+'], i + 1):
                        yield content
            if '#' in node._children and (normal or i > 0):
                content = node._children['#']._content
                if content is not None:
                    yield content

        return rec(self._root)


class MessageRouterData(HasTraits):
    """
    A class that stores topics and their subscribers, with MQTT-style wildcards.

    It follows the guidelines from here: https://eclipse.dev/paho/files/mqttdoc/MQTTClient/html/wildcard.html

    As it states in the link above:
    To provide more flexibility, MQTT supports a hierarchical topic namespace. This allows application designers to
    organize topics to simplify their management. Levels in the hierarchy are delimited by the '/' character,
    such as SENSOR/1/HUMIDITY. Publishers and subscribers use these hierarchical topics as already described.

    For subscriptions, two wildcard characters are supported:

   - A '#' character represents a complete sub-tree of the hierarchy and thus must be the last character in a
   subscription topic string, such as SENSOR/#. This will match any topic starting with SENSOR/,
   such as SENSOR/1/TEMP and SENSOR/2/HUMIDITY.

    - A '+' character represents a single level of the hierarchy and is used between delimiters. For
    example, SENSOR/+/TEMP will match SENSOR/1/TEMP and SENSOR/2/TEMP.

    - Publishers are not allowed to use the wildcard characters in their topic names.

    - Deciding on your topic hierarchy is an important step in your system design.

    The matcher here will pass all the tests here: https://github.com/eclipse/paho.mqtt.python/blob/master/tests/test_matcher.py

    We are using the same matcher as the one in the link above.

    This will also be shown in the pytest module for this project.

    Attributes:
        topic_subscriber_map (Dict): A dictionary mapping topics to a list of their subscribing actor names.

    Preconditions:
        - `topic` should be a string.
        - `subscribing_actor_name` should be a string.
        - Topics can contain wildcards '+' for single level and '#' for multiple levels. The '#' character must be the last character in the subscription topic string.

    Example:

        # while assigning subscribers top topics, you can use wildcards in teh topics

        >>> router_data = MessageRouterData()
        >>> router_data.add_subscriber_to_topic("SENSOR/+", "actor1")
        >>> router_data.add_subscriber_to_topic("SENSOR/1/HUMIDITY", "actor2")
        >>> router_data.add_subscriber_to_topic("SENSOR/#", "actor3")
        >>> router_data.add_subscriber_to_topic("SENSOR/2/TEMP", "actor4")

        # While trying to find subscribers for a certain topic published, you cannot use wildcards in the topics
        >>> sorted(router_data.get_subscribers_for_topic("SENSOR/1/HUMIDITY"))
        ['actor2', 'actor3']
        >>> sorted(router_data.get_subscribers_for_topic("SENSOR/1/TEMP"))
        ['actor3']
        >>> sorted(router_data.get_subscribers_for_topic("SENSOR/2/TEMP"))
        ['actor3', 'actor4']
        >>> sorted(router_data.get_subscribers_for_topic("SENSOR/1"))
        ['actor1', 'actor3']
        >>> router_data.get_subscribers_for_topic("NONEXISTENT")
        []
    """
    topic_subscriber_map = Instance('RedisHashDictProxy',
                                    desc="A dictionary of topics and a list of tuples containing topic subscribed "
                                         "actor name, listening queue pairs stored in redis as a hash")

    storage_key_name = Str(DEFAULT_STORAGE_KEY_NAME, desc="The name of the redis key under which this data will be "
                                                          "stored")
    listener_queue = Str("default", desc="The unique queue for a message router actor that it is listening to")

    # ------- default trait setters ----------- #

    # ------- trait change handler ---------#

    def _topic_subscriber_map_default(self):
        return RedisHashDictProxy(redis_client=dramatiq.get_broker().client, hash_name=self.storage_key_name)

    def add_subscriber_to_topic(self, topic: Str, subscribing_actor_name: Str):
        """
        Adds a subscriber to a specific topic.

        Args:
            topic (str): The topic to subscribe to.
            subscribing_actor_name (str): The name of the subscribing actor.

        Preconditions:
            - `topic` should be a valid string.
            - `subscribing_actor_name` should be a valid string.

        Example:
            >>> router_data = MessageRouterData()
            >>> router_data.add_subscriber_to_topic("SENSOR/+", "actor1")
            >>> router_data.topic_subscriber_map
            {'SENSOR/+': ['actor1', 'queue_name']}

        """

        # initialize topic with the sub actor. listener queue pair if it does not exist
        if topic not in self.topic_subscriber_map:
            self.topic_subscriber_map[topic] = [(subscribing_actor_name, self.listener_queue)]

        # if the sub actor, listener queue pair is not a value for the topic, then add it
        elif [subscribing_actor_name, self.listener_queue] not in self.topic_subscriber_map[topic]:
            self.topic_subscriber_map[topic] += [(subscribing_actor_name, self.listener_queue)]

    def remove_subscriber_from_topic(self, topic: Str, subscribing_actor_name: Str):
        """
        Removes a subscriber, listener queue pair from a specific topic.
        If the topic has no more subscribers, it is removed from the map.

        Args:
            topic (str): The topic to unsubscribe from.
            subscribing_actor_name (str): The name of the subscribing actor.

        Preconditions:
            - `topic` should be a valid string.
            - `subscribing_actor_name` should be a valid string.

        Example:
            >>> router_data = MessageRouterData()
            >>> router_data.add_subscriber_to_topic("SENSOR/+", "actor1")
            >>> router_data.remove_subscriber_from_topic("SENSOR/+", "actor1")
            >>> router_data.topic_subscriber_map
            {}

        """
        if topic in self.topic_subscriber_map:
            new_list = self.topic_subscriber_map[topic]
            new_list.remove([subscribing_actor_name, self.listener_queue])

            if len(new_list) == 0:
                del self.topic_subscriber_map[topic]

            else:
                self.topic_subscriber_map[topic] = new_list

    def get_subscribers_for_topic(self, topic: str) -> list:
        """
        Gets the list of subscribers for a specific topic. Supports MQTT-style wildcard patterns.

        Args:
            topic (str): The topic to get subscribers for.

        Returns:
            list: A list of subscribers for the topic.

        Preconditions:
            - `topic` should be a valid string.

        """
        bytes_to_str = lambda x: x.decode() if isinstance(x, bytes) else x

        subscribers = set()
        for key, value in self.topic_subscriber_map.items():
            key = bytes_to_str(key)
            value = bytes_to_str(value)

            if self._topic_matches_pattern(key, topic):
                for actor in value:
                    subscribers.add(tuple(actor))

        return list(subscribers)

    @staticmethod
    def _topic_matches_pattern(pattern: str, topic: str) -> bool:
        """
        Checks if a topic matches a pattern with MQTT-style wildcards.

        This method was taken from here: https://github.com/eclipse/paho.mqtt.python/blob/master/src/paho/mqtt/client.py

        Args:
            pattern (str): The pattern with wildcards.
            topic (str): The topic to check.

        Returns:
            bool: True if the topic matches the pattern, False otherwise.

        Preconditions:
            - `pattern` should be a valid string.
            - `topic` should be a valid string.

        Example:
            >>> MessageRouterData._topic_matches_pattern("SENSOR/+", "SENSOR/1")
            True
            >>> MessageRouterData._topic_matches_pattern("SENSOR/+", "SENSOR/1/HUMIDITY")
            False
            >>> MessageRouterData._topic_matches_pattern("SENSOR/#", "SENSOR/1/HUMIDITY")
            True
            >>> MessageRouterData._topic_matches_pattern("SENSOR/#", "SENSOR")
            True
            >>> MessageRouterData._topic_matches_pattern("SENSOR/+", "SENSOR")
            False
        """
        matcher = MQTTMatcher()
        matcher[pattern] = True
        try:
            next(matcher.iter_match(topic))
            return True
        except StopIteration:
            return False


class MessageRouterActor(DramatiqControllerBase):
    """
    A class that routes messages to subscribers based on topics.

    Each instance of this class has one message router actor with a specific queue unique to it.
    """

    ######## Message Router Interface #######################################################
    message_router_data = Instance(MessageRouterData)

    def _message_router_data_default(self):
        return MessageRouterData(listener_queue=self.listener_queue)

    ##################### Dramatiq Controller Base Interface #######################

    def _listener_actor_method_default(self):
        """returns a default listener actor method for message routing"""

        def listener_actor_method(timestamped_message: TimestampedMessage, topic: Str):
            logger.debug(f"MESSAGE_ROUTER: Received message: {timestamped_message} on topic: {topic}")

            subscribing_actor_queue_info = self.message_router_data.get_subscribers_for_topic(topic)

            for subscribing_actor, queue in subscribing_actor_queue_info:
                logger.debug(f"MESSAGE_ROUTER: Publishing message: {timestamped_message} to actor: {subscribing_actor}")    

                publish_message(str(timestamped_message), topic, subscribing_actor, queue_name=queue, message_kwargs={"timestamp": timestamped_message._timestamp_ms})

            logger.debug(
                f"MESSAGE_ROUTER: Message: {timestamped_message} on topic {topic} published to {len(subscribing_actor_queue_info)} subscribers")

        return listener_actor_method
