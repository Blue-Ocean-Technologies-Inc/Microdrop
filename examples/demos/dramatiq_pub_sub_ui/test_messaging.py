import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.broker_server_helpers import dramatiq_workers_context

def main(message, topic):
    with dramatiq_workers_context():
        publish_message(message, topic)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])