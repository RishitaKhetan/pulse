"""
Pulse CLI: commands for starting the server, managing data, and configuration.
"""

import argparse
import json
import shutil
from pathlib import Path

from pulse.server import DEFAULT_DATA_DIR, run_server


def cmd_start(args):
    """Start the Pulse server and open the dashboard."""
    run_server(port=args.port, open_browser=not args.no_browser, data_dir=args.data_dir)


def cmd_reset(args):
    """Clear all event data."""
    if not args.data_dir.exists():
        print(f"No data to reset at {args.data_dir}")
        return

    shutil.rmtree(args.data_dir)
    print(f"[OK] Cleared all data from {args.data_dir}")


def cmd_init(args):
    """Initialize Pulse configuration."""
    config_dir = Path.home() / ".pulse"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.json"

    default_config = {
        "data_dir": str(DEFAULT_DATA_DIR),
        "port": 4747,
        "open_browser": True,
    }

    if config_file.exists():
        print(f"Config already exists at {config_file}")
        return

    with open(config_file, "w") as f:
        json.dump(default_config, f, indent=2)
    print(f"[OK] Created config at {config_file}")


def cmd_demo_data(args):
    """Populate dashboard with sample events."""
    import random
    from pulse.models import Event
    from pulse.storage import EventStore

    store = EventStore(data_dir=args.data_dir)
    store.start()

    # Sample data
    users = ["alice", "bob", "charlie", "diana", "eve", "frank"]
    pages = ["/home", "/pricing", "/features", "/docs", "/signup", "/dashboard"]
    buttons = ["start_trial", "view_pricing", "contact_us", "read_docs", "upgrade"]

    events = []
    for _ in range(100):
        user = random.choice(users)

        # Mix of different event types
        event_type = random.choice(["page_view", "button_click", "signup"])

        if event_type == "page_view":
            events.append(Event(
                event_name="page_view",
                user_id=user,
                properties={"page": random.choice(pages)}
            ))
        elif event_type == "button_click":
            events.append(Event(
                event_name="button_click",
                user_id=user,
                properties={"button": random.choice(buttons)}
            ))
        else:  # signup
            events.append(Event(
                event_name="signup",
                user_id=user,
                properties={"plan": random.choice(["free", "pro"])}
            ))

    store.add_many(events)
    store.flush()
    store.stop()

    print(f"[OK] Generated {len(events)} sample events at {args.data_dir}")


def main():
    parser = argparse.ArgumentParser(
        prog="pulse",
        description="Pulse — a local analytics dashboard for your app.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Start command
    start_parser = subparsers.add_parser(
        "start", help="Start the local Pulse server and open the dashboard"
    )
    start_parser.add_argument(
        "--port", type=int, default=4747,
        help="Port to run Pulse on (default: 4747)",
    )
    start_parser.add_argument(
        "--no-browser", action="store_true",
        help="Don't automatically open the dashboard in a browser",
    )
    start_parser.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR,
        help=f"Directory to store event data (default: {DEFAULT_DATA_DIR})",
    )
    start_parser.set_defaults(func=cmd_start)

    # Reset command
    reset_parser = subparsers.add_parser(
        "reset", help="Clear all event data"
    )
    reset_parser.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR,
        help=f"Directory to clear (default: {DEFAULT_DATA_DIR})",
    )
    reset_parser.set_defaults(func=cmd_reset)

    # Init command
    init_parser = subparsers.add_parser(
        "init", help="Initialize Pulse configuration"
    )
    init_parser.set_defaults(func=cmd_init)

    # Demo data command
    demo_parser = subparsers.add_parser(
        "demo-data", help="Populate dashboard with sample events"
    )
    demo_parser.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR,
        help=f"Directory to store demo data (default: {DEFAULT_DATA_DIR})",
    )
    demo_parser.set_defaults(func=cmd_demo_data)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()