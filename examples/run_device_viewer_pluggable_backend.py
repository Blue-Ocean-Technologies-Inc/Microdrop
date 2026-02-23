import sys
from pathlib import Path

# add microdrop module to path to access other submodules in microdrop (e.g. microdrop_utils)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from examples.run_device_viewer_pluggable import main as run_device_viewer_pluggable
from examples.plugin_consts import *

def main(args):
    """Run only the backend plugins."""

    plugins = REQUIRED_PLUGINS + BACKEND_PLUGINS

    # You can now access the validated device choice here
    print(f"Starting with device: {args.device}")

    if args.device == "dropbot":
        plugins += DROPBOT_BACKEND_PLUGINS
    elif args.device == "opendrop":
        plugins += OPENDROP_BACKEND_PLUGINS

    run_device_viewer_pluggable(
        plugins=plugins,
        contexts=REQUIRED_CONTEXT,
        application=BACKEND_APPLICATION,
        persist=True
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the frontend device viewer plugins.")

    parser.add_argument(
        "--device",
        type=str,
        choices=["dropbot", "opendrop"],
        default="dropbot",  # Sets a default if the user doesn't provide the flag
        help="Specify the device to use: 'dropbot' or 'opendrop'"
    )
    main(parser.parse_args())
