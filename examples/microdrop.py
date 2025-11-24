from .plugin_consts import REQUIRED_PLUGINS, FRONTEND_PLUGINS, BACKEND_PLUGINS, REQUIRED_CONTEXT, SERVER_CONTEXT, DEFAULT_APPLICATION
from .run_device_viewer_pluggable import main

def microdrop():
    main(
        plugins=REQUIRED_PLUGINS + FRONTEND_PLUGINS + BACKEND_PLUGINS,
        contexts=SERVER_CONTEXT + REQUIRED_CONTEXT,
        application=DEFAULT_APPLICATION,
        persist=False # UI so no
         )

if __name__ == '__main__':
    microdrop()