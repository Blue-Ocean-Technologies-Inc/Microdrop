from microdrop_utils.app_setup_helpers import microdrop_runner_setup
microdrop_runner_setup()

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
