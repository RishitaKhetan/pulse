"""
This file defines the `pulse` command itself.

When someone types `pulse start` in their terminal, Python runs the
`main()` function below. Right now it only knows one command: "start".
Later we'll add more, like `pulse init` or `pulse reset`.
"""

import argparse

from pulse.server import run_server


def main():
    # argparse is a built-in tool that reads what the user typed
    # after "pulse" and figures out what they want to do.
    parser = argparse.ArgumentParser(
        prog="pulse",
        description="Pulse — a local analytics dashboard for your app.",
    )
    subparsers = parser.add_subparsers(dest="command")

    start_parser = subparsers.add_parser(
        "start", help="Start the local Pulse server and open the dashboard"
    )
    start_parser.add_argument(
        "--port",
        type=int,
        default=4747,
        help="Port to run Pulse on (default: 4747)",
    )
    start_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't automatically open the dashboard in a browser",
    )

    args = parser.parse_args()

    if args.command == "start":
        run_server(port=args.port, open_browser=not args.no_browser)
    else:
        # If someone just types "pulse" with no command, show them the help text
        parser.print_help()


if __name__ == "__main__":
    main()