from dramatiq import get_broker

from microdrop_application.consts import APP_GLOBALS_REDIS_HASH
from microdrop_utils.redis_manager import get_redis_hash_proxy


def sync_redis_globals(key, set_value=None):
    """
    returns value already in cache or sets key to set_value if provided.
    """
    # try to get key from app globals
    app_globals = get_redis_hash_proxy(redis_client=get_broker().client, hash_name=APP_GLOBALS_REDIS_HASH)

    globals_value = app_globals.get(key)

    if globals_value:
        return globals_value

    elif set_value:
        # push value to globals if its not there and new value given
        app_globals[key] = set_value
        return set_value

    return None