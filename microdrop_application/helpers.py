from pathlib import Path

from microdrop_application.consts import APP_GLOBALS_REDIS_HASH, EXPERIMENT_DIR
from microdrop_utils.redis_manager import get_redis_hash_proxy
from dramatiq import get_broker

def get_microdrop_redis_globals_manager():
    return get_redis_hash_proxy(redis_client=get_broker().client, hash_name=APP_GLOBALS_REDIS_HASH)


def get_current_experiment_directory() -> Path:
    """Return the currently-active experiment folder.

    Usable from plugins/widgets that don't have direct access to the Envisage
    application instance. Mirrors MicrodropApplication._get_current_experiment_directory
    / MicrodropBackendApplication._get_current_experiment_directory.
    """
    # Avoid importing MicrodropPreferences at module load — it pulls Traits
    # machinery that may not be ready when helpers.py is first imported.
    from microdrop_application.preferences import MicrodropPreferences

    globals_manager = get_microdrop_redis_globals_manager()
    current_exp_dir = globals_manager.get("experiment_directory", None)
    if current_exp_dir is None:
        current_exp_dir = EXPERIMENT_DIR
        globals_manager["experiment_directory"] = EXPERIMENT_DIR

    experiments_root = Path(MicrodropPreferences().EXPERIMENTS_DIR)
    return experiments_root / current_exp_dir