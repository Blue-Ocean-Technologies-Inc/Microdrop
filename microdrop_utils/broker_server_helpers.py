import subprocess
import time
from contextlib import contextmanager
import os

from dramatiq import get_broker, Worker
from dramatiq.middleware import CurrentMessage

from logger.logger_service import get_logger
logger = get_logger(__name__)


def is_redis_running():
    """Check if Redis is running by attempting to connect to it."""
    import redis
    try:
        client = redis.StrictRedis(host='localhost', port=6379)
        client.ping()
        return True
    except redis.exceptions.ConnectionError:
        return False


def start_redis_server(retries=5, wait=3):
    """Start the Redis server."""
    process = None
    if not is_redis_running():
        process = subprocess.Popen(["redis-server", f"{os.path.dirname(__file__)}{os.sep}redis.conf"])
        for _ in range(retries):  # Retry up to 5 times
            if is_redis_running():
                print("Redis server is running.")
                return process
            else:
                print("Waiting for Redis server to start...")
                time.sleep(wait)
        print("Failed to start Redis server.")
        process.terminate()

    else:
        print("Redis server is already running.")
    return process


def stop_redis_server(process):
    """Stop the Redis server."""
    if process is None:
        print("Redis server is not running, so no need to stop it.")
        return
    else:
        try:
            process.terminate()
            print("Redis server stopped.")
        except Exception as e:
            print(f"Failed to stop Redis server: {e}")


def remove_middleware_from_dramatiq_broker(middleware_name: str, broker: 'dramatiq.broker.Broker'):
    # Remove Prometheus middleware if it exists
    broker.middleware[:] = [
        m for m in broker.middleware
        if m.__module__ != middleware_name
    ]


def start_workers(**kwargs) -> 'dramatiq.worker.Worker':
    """
    A startup routine for apps that make use of dramatiq.
    """
    
    BROKER = get_broker()
    
    # Add the CurrentMessage middleware so you we can inspect the timestamp
    BROKER.add_middleware(CurrentMessage())
    
    # Flush any old messages, start the worker, then run your app logic
    BROKER.flush_all()
    worker = Worker(broker=BROKER, **kwargs)
    worker.start()

    return worker


@contextmanager
def redis_server_context():
    """
    Context manager for apps that make use of a redis server
    """
    process = None
    try:
        process = start_redis_server()

        yield  # This is where the main logic will execute within the context

    finally:
        # Shutdown routine
        stop_redis_server(process)


@contextmanager
def dramatiq_workers_context(**kwargs):
    """
    Context manager for apps that make use of dramatiq. They need the workers to exist.
    """
    remove_middleware_from_dramatiq_broker(middleware_name="dramatiq.middleware.prometheus", broker=get_broker())
    try:
        worker = start_workers(**kwargs)

        yield worker  # This is where the main logic will execute within the context

    finally:
        # Shutdown routine
        worker.stop()


# Example usage
if __name__ == "__main__":
    from microdrop_utils.dramatiq_pub_sub_helpers import publish_message, MessageRouterActor
    import dramatiq


    def example_app_routine():
        # Given that I have a database
        database = {}

        @dramatiq.actor
        def put(message, topic):
            database[topic] = message

        test_topic = "test_topic"
        test_message = "test_message"
        # after declaring the actor, I add it to the message router and ascribe an topic to it that it will listen to.
        mra = MessageRouterActor()
        mra.message_router_data.add_subscriber_to_topic(topic=test_topic, subscribing_actor_name="put")
        # Now I publish a message to the message router actor to the test topic for triggering it.
        publish_message(test_message, test_topic, "message_router_actor")
        publish_message(message="test", topic="test")
        while True:
            if test_topic in database:
                print(f"Message: {database[test_topic]} successfully published on topic {test_topic}")
                exit(0)


    with redis_server_context(), dramatiq_workers_context():
            example_app_routine()
