import sys
from PySide6.QtWidgets import QApplication
from dramatiq import get_broker, Worker
from dramatiq.middleware import CurrentMessage
from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterActor


def main():

    # import the MainWindow and MainWindowController classes from the dramatiq_ui module
    from examples.dropbot_pub_sub.ui import MainWindow, MainWindowController

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
    BROKER.middleware[:] = [
        m for m in BROKER.middleware
        if m.__module__ != "dramatiq.middleware.prometheus"
    ]

    # Add the CurrentMessage middleware so you we can inspect the timestamp
    BROKER.add_middleware(CurrentMessage())
    
    # Flush any old messages, start the worker, then run your app logic
    BROKER.flush_all()
    worker = Worker(broker=BROKER)
    worker.start()
    main()
