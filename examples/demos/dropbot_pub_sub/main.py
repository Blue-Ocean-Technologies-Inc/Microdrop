# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import sys
from PySide6.QtWidgets import QApplication
from dramatiq import get_broker, Worker
from dramatiq.middleware import CurrentMessage
from microdrop_utils.broker_server_helpers import remove_middleware_from_dramatiq_broker
from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterActor


def main():

    # import the MainWindow and MainWindowController classes from the dramatiq_ui module
    from examples.demos.dropbot_pub_sub.ui import MainWindow, MainWindowController

    app = QApplication(sys.argv)
    # create an instance of the MainWindow class
    window = MainWindow()
    # create an instance of the MainWindowController class
    window_controller = MainWindowController(window)


    # initialize pubsub actor
    router_actor = MessageRouterActor()

    # add subscribers to topics
    for actor_name, topics_list in window_controller.actor_topics_dict.items():
        for topic in topics_list:
            router_actor.message_router_data.add_subscriber_to_topic(topic, actor_name)

    # show the window
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":

    BROKER = get_broker()

    # Remove Prometheus middleware
    remove_middleware_from_dramatiq_broker(middleware_name="dramatiq.middleware.prometheus", broker=BROKER)

    # Add the CurrentMessage middleware so you we can inspect the timestamp
    BROKER.add_middleware(CurrentMessage())
    
    # Flush any old messages, start the worker, then run your app logic
    BROKER.flush_all()
    worker = Worker(broker=BROKER)
    worker.start()
    main()
