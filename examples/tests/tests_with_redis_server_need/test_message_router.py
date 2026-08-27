# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import pytest
import dramatiq
from ..common import worker
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message


class TestMessageRouterData:
    """
    Tests on get_subscribers_for_topic function in the MessageRouterData class
    """

    @pytest.fixture
    def router_data(self):
        """
        Fixture to initialize a MessageRouterData instance.

        Returns:
            MessageRouterData: An instance of MessageRouterData.
        """
        from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterData

        return MessageRouterData(listener_queue="default")

    def test_add_subscriber_to_topic(self, router_data):
        """
        Test adding subscribers to a topic.

        Args:
            router_data (MessageRouterData): The message router data instance.
        """
        router_data.add_subscriber_to_topic("x", "actor1")
        assert ["actor1"], "default" == router_data.topic_subscriber_map["x"]
        router_data.add_subscriber_to_topic("x", "actor2")
        assert router_data.topic_subscriber_map["x"] == [["actor1", "default"], ["actor2", "default"]]

    def test_remove_subscriber_from_topic(self, router_data):
        """
        Test removing subscribers from a topic.

        Args:
            router_data (MessageRouterData): The message router data instance.
        """
        router_data.add_subscriber_to_topic("x", "actor1")
        router_data.add_subscriber_to_topic("x", "actor2")
        router_data.remove_subscriber_from_topic("x", "actor1")
        assert router_data.topic_subscriber_map["x"] == [["actor2", "default"]]
        router_data.remove_subscriber_from_topic("x", "actor2")
        assert "x" not in router_data.topic_subscriber_map

    @pytest.mark.parametrize("sub, topic", [
        ("foo/bar", "foo/bar"),
        ("foo/+", "foo/bar"),
        ("foo/+/baz", "foo/bar/baz"),
        ("foo/+/#", "foo/bar/baz"),
        ("A/B/+/#", "A/B/B/C"),
        ("#", "foo/bar/baz"),
        ("#", "/foo/bar"),
        ("/#", "/foo/bar"),
        ("$SYS/bar", "$SYS/bar"),
    ])
    def test_matching(self, router_data, sub, topic):
        router_data.add_subscriber_to_topic(sub, "test_actor")
        assert ("test_actor", "default") in router_data.get_subscribers_for_topic(topic)

    @pytest.mark.parametrize("sub, topic", [
        ("test/6/#", "test/3"),
        ("foo/bar", "foo"),
        ("foo/+", "foo/bar/baz"),
        ("foo/+/baz", "foo/bar/bar"),
        ("foo/+/#", "fo2/bar/baz"),
        ("/#", "foo/bar"),
        ("#", "$SYS/bar"),
        ("$BOB/bar", "$SYS/bar"),
    ])
    def test_not_matching(self, router_data, sub, topic):
        router_data.add_subscriber_to_topic(sub, "test_actor")
        assert ("test_actor", "default") not in router_data.get_subscribers_for_topic(topic)


class TestMessageRouterActor:
    """
    Tests on the MessageRouterActor class.
    """

    @pytest.fixture(scope="module")
    def router_actor(self):
        """
        Fixture to initialize a MessageRouterActor instance.

        Returns:
            MessageRouterActor: An instance of MessageRouterActor.
        """
        from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterActor

        return MessageRouterActor()

    def test_message_router_actor_can_route_message(self, router_actor):
        broker = dramatiq.get_broker()

        # Given that I have a database
        database = {}

        # And an actor that can write data to that database
        @dramatiq.actor
        def put(message, topic):
            database[topic] = message

        test_topic = "test_topic"
        test_message = "test_message"

        # after declaring the actor, I add it to the message router and ascribe an topic to it that it will listen to.
        router_actor.message_router_data.add_subscriber_to_topic(topic=test_topic, subscribing_actor_name="put")

        # Now I publish a message to the message router actor to the test topic for triggering it.
        publish_message(test_message, test_topic, "message_router_actor")

        with worker(broker, worker_timeout=100):
            # And I give the workers time to process the messages
            broker.join("default")

        # I expect the database to be populated
        assert database == {test_topic: test_message}

    def test_message_router_actor_can_route_message_to_multiple_subscribing_actors(self, router_actor):
        # Given that I have two databases
        database1 = {}
        database2 = {}
        database3 = {}

        # And actors that can write data to these databases
        @dramatiq.actor
        def put1(message, topic):
            database1[topic] = message

        @dramatiq.actor
        def put2(message, topic):
            database2[topic] = message

        @dramatiq.actor
        def put3(message, topic):
            database3[topic] = message

        test_topic = "test_topic"
        test_message = "test_message"

        # after declaring the actors, I add to the message router and ascribe topics.
        router_actor.message_router_data.add_subscriber_to_topic(topic=f"{test_topic}/#", subscribing_actor_name="put1")
        router_actor.message_router_data.add_subscriber_to_topic(topic=f"{test_topic}/y", subscribing_actor_name="put2")
        router_actor.message_router_data.add_subscriber_to_topic(topic=f"{test_topic}/y/+",
                                                                 subscribing_actor_name="put3")

        # Now I publish a message to the message router actor to the test topic for triggering it.
        publish_message(test_message, test_topic, "message_router_actor")
        # this should only trigger the one actor that is subscribed to the topic

        # Now I publish a message to the message router actor to the test topic.y for triggering it.
        publish_message(test_message, test_topic + "/y", "message_router_actor")
        # this should trigger the two actors that are subscribed to the topic and the topic.y (the subtopic)

        # Now I publish a message to the message router actor to the test topic.y.1 for triggering it.
        publish_message(test_message, test_topic + "/y/z", "message_router_actor")
        # this should trigger the three actors that are subscribed to the topic, the topic/y/* (the subtopic) and the
        # topic/# (the sub

        broker = dramatiq.get_broker()
        with worker(broker, worker_timeout=100) as current_worker:
            broker.join("default")
            current_worker.join()

        # I expect the database to be populated like so
        assert database1 == {test_topic: test_message, test_topic + "/y": test_message,
                             test_topic + "/y/z": test_message}

        assert database2 == {test_topic + "/y": test_message}

        assert database3 == {test_topic + "/y/z": test_message}


if __name__ == "__main__":
    pytest.main()
