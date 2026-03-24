import sys
from pathlib import Path

from microdrop_utils.broker_server_helpers import configure_dramatiq_broker

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def microdrop_runner_setup():
    """
    Common setup for all MicroDrop runner scripts.

    Configures the Dramatiq broker from redis_settings.json and adds
    the project root to sys.path so submodules are importable.

    Must be called before importing any modules that use dramatiq.get_broker().
    """
    configure_dramatiq_broker()
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))