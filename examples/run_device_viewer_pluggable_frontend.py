from microdrop_utils.app_setup_helpers import microdrop_runner_setup
microdrop_runner_setup()

from examples.run_device_viewer_pluggable import main as run_device_viewer_pluggable
from examples.plugin_consts import REQUIRED_PLUGINS, FRONTEND_PLUGINS, REQUIRED_CONTEXT, FRONTEND_APPLICATION, \
    DROPBOT_FRONTEND_PLUGINS, OPENDROP_FRONTEND_PLUGINS, SERVICE_PLUGINS


def main(args):
    """Run only the frontend plugins."""

    # You can now access the validated device choice here
    print(f"Starting with device: {args.device}")

    plugins = REQUIRED_PLUGINS + FRONTEND_PLUGINS + SERVICE_PLUGINS

    if args.device == "dropbot":
        plugins += DROPBOT_FRONTEND_PLUGINS
    elif args.device == "opendrop":
        plugins += OPENDROP_FRONTEND_PLUGINS

    run_device_viewer_pluggable(
        plugins=plugins,
        contexts=REQUIRED_CONTEXT,
        application=FRONTEND_APPLICATION,
        persist=False
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the frontend device viewer plugins.")

    parser.add_argument(
        "--device",
        type=str,
        choices=["dropbot", "opendrop"],
        default="dropbot", # Sets a default if the user doesn't provide the flag
        help="Specify the device to use: 'dropbot' or 'opendrop'"
    )
    main(parser.parse_args())
