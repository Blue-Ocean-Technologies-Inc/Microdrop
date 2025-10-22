from microdrop_application.consts import APP_GLOBALS_REDIS_HASH
from microdrop_utils.redis_manager import get_redis_hash_proxy
from dramatiq import get_broker

def get_microdrop_redis_globals_manager():
    return get_redis_hash_proxy(redis_client=get_broker().client, hash_name=APP_GLOBALS_REDIS_HASH)