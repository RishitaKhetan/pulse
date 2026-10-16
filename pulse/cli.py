"""
Pulse CLI: commands for starting the server, managing data, and configuration.
"""

import argparse
import json
import shutil
from pathlib import Path

from pulse.server import DEFAULT_DATA_DIR, run_server

DEFAULT_PORT = 4747


def config_path() -> Path:
    """Where `pulse init` saves settings: ~/.pulse/config.json"""
    return Path.home() / ".pulse" / "config.json"


def load_config() -> dict:
    """Read the config file if it exists. Missing or broken file -> empty dict (use defaults)."""
    path = config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        print(f"[WARN] Could not read {path}, using default settings")
        return {}


def resolve_data_dir(args, config: dict) -> Path:
    """Pick the data folder: --data-dir flag first, then config file, then the default."""
    if args.data_dir is not None:
        return args.data_dir
    return Path(config.get("data_dir", DEFAULT_DATA_DIR)).expanduser()


def cmd_start(args):
    """Start the Pulse server and open the dashboard."""
    config = load_config()
    # Each setting: command-line flag wins, then config file, then built-in default
    port = args.port if args.port is not None else config.get("port", DEFAULT_PORT)
    open_browser = False if args.no_browser else config.get("open_browser", True)
    data_dir = resolve_data_dir(args, config)
    run_server(port=port, open_browser=open_browser, data_dir=data_dir)


def cmd_reset(args):
    """Clear all event data."""
    # Use the same folder `pulse start` uses, so reset clears the right data
    data_dir = resolve_data_dir(args, load_config())
    if not data_dir.exists():
        print(f"No data to reset at {data_dir}")
        return

    shutil.rmtree(data_dir)
    print(f"[OK] Cleared all data from {data_dir}")


def cmd_init(args):
    """Initialize Pulse configuration."""
    config_file = config_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)

    default_config = {
        "data_dir": str(DEFAULT_DATA_DIR),
        "port": DEFAULT_PORT,
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

    data_dir = resolve_data_dir(args, load_config())
    store = EventStore(data_dir=data_dir)
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

    print(f"[OK] Generated {len(events)} sample events at {data_dir}")


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
        "--port", type=int, default=None,
        help="Port to run Pulse on (default: config file, else 4747)",
    )
    start_parser.add_argument(
        "--no-browser", action="store_true",
        help="Don't automatically open the dashboard in a browser",
    )
    start_parser.add_argument(
        "--data-dir", type=Path, default=None,
        help=f"Directory to store event data (default: config file, else {DEFAULT_DATA_DIR})",
    )
    start_parser.set_defaults(func=cmd_start)

    # Reset command
    reset_parser = subparsers.add_parser(
        "reset", help="Clear all event data"
    )
    reset_parser.add_argument(
        "--data-dir", type=Path, default=None,
        help=f"Directory to clear (default: config file, else {DEFAULT_DATA_DIR})",
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
        "--data-dir", type=Path, default=None,
        help=f"Directory to store demo data (default: config file, else {DEFAULT_DATA_DIR})",
    )
    demo_parser.set_defaults(func=cmd_demo_data)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()