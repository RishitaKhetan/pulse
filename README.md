# Pulse Analytics

A plug-and-play local analytics dashboard for developers. Run one command, get instant insights into your app's events—no Docker, no cloud accounts, no setup.

```bash
pulse start
```

That's it. Your analytics dashboard opens at `http://localhost:4747`.

## Features

- **📊 Event tracking** - Track any event in your app (page views, button clicks, signups, errors, etc.)
- **🎯 Real-time dashboard** - See trends and counts as events flow in
- **🔗 Funnel analysis** - Understand where users drop off
- **📈 Retention metrics** - Track how many users come back
- **🧪 A/B testing** - Run experiments with built-in statistical analysis
- **⚡ Fast & local** - All data stays on your machine; queries run in under 1 second
- **🐍 Python & JS SDKs** - Track events from any backend or frontend

## Installation

```bash
pip install pulse-analytics
```

Requires Python 3.10+.

## Quick Start

### 1. Start the dashboard

```bash
pulse start
```

Opens `http://localhost:4747` automatically. Stop with `Ctrl+C`.

### 2. Initialize (optional config)

```bash
pulse init
```

Creates `~/.pulse/config.json` with default settings. Edit to customize port or data directory.

### 3. Send events

#### Python

```python
import pulse

pulse.init()  # Call once at app startup

# Track an event
pulse.track("page_view", user_id="alice", properties={"page": "/home"})
pulse.track("button_click", user_id="alice", properties={"button": "signup"})

# Flush before exit (or auto-flushes every 30 seconds)
pulse.flush()
```

#### JavaScript/TypeScript

```javascript
// In your HTML or bundled app
<script src="http://localhost:4747/pulse.js"></script>

<script>
  Pulse.init();
  
  // Track an event
  Pulse.track("page_view", "alice", { page: "/home" });
  Pulse.track("button_click", "alice", { button: "signup" });
  
  // Flush on page unload (or auto-flushes every 10 seconds)
  window.addEventListener("beforeunload", () => Pulse.flush());
</script>
```

## CLI Commands

```bash
# Start the dashboard server
pulse start [--port 4747] [--no-browser] [--data-dir ~/.pulse/data/events]

# Initialize configuration
pulse init

# Load sample data for testing
pulse demo-data

# Clear all events
pulse reset
```

## Event Format

Every event sent to Pulse has this structure:

```json
{
  "event_name": "page_view",           // What happened (e.g., click, signup, error)
  "user_id": "alice",                  // Who did it (user ID, anonymous ID, etc.)
  "timestamp": "2026-10-10T15:30:45Z", // When (ISO format, UTC)
  "properties": {                      // Extra details (optional)
    "page": "/home",
    "referrer": "google.com"
  }
}
```

## Dashboard

The dashboard includes:

- **Overview** - Event counts and trends over time
- **Top users** - Most active users
- **Funnels** - Multi-step conversion paths (e.g., view pricing → click button → signup)
- **Retention** - How many users returned each day
- **Experiments** - Create and analyze A/B tests

## A/B Testing

```python
# Create an experiment
pulse.experiment(
    name="signup_button",
    variants=["blue", "red"],
    goal_event="signup"
)

# Assign a user to a variant (deterministic)
variant = pulse.experiment_variant("signup_button", user_id="alice")
# Returns "blue" or "red" — same user always gets the same variant

# Log the variant with your event
pulse.track("signup", user_id="alice", properties={"variant": variant})

# View results in the dashboard or via API
# GET /experiments/signup_button/results
```

Results include:
- Conversion rate per variant
- Statistical significance (p-value)
- Confidence intervals

## Configuration

Edit `~/.pulse/config.json`:

```json
{
  "data_dir": "/home/user/.pulse/data/events",
  "port": 4747,
  "open_browser": true
}
```

## Performance

- Dashboard query: **< 1 second** for 1M events
- SDK overhead: **< 2%** on your app
- Experiment analysis: **< 5 seconds**

## Data Storage

Events are stored as Parquet files in `~/.pulse/data/events/` (configurable). Each day gets a folder:

```
~/.pulse/data/events/
  2026-10-10/
    00_1728547800.parquet
    01_1728548100.parquet
  2026-10-11/
    00_1728634200.parquet
```

To back up your data, just copy the folder. To clear everything:

```bash
pulse reset
```

## Examples

### Track a sign-up
```python
pulse.track("signup", user_id="alice", properties={"plan": "pro"})
```

### Track an error
```python
pulse.track("error", user_id="bob", properties={
  "message": "Failed to load dashboard",
  "error_code": 500
})
```

### Track an API latency
```python
pulse.track("api_request", user_id="charlie", properties={
  "endpoint": "/api/users",
  "latency_ms": 245,
  "status": 200
})
```

## Troubleshooting

**Q: The dashboard won't open in my browser**
- Make sure port 4747 is not in use: `pulse start --port 5000`
- Or open manually: `http://localhost:4747`

**Q: Events aren't showing up**
- Check that your app calls `pulse.init()` before tracking
- Make sure the server is running (`pulse start`)
- Check the console for errors in your app

**Q: I forgot to flush events before my app crashed**
- Pulse auto-flushes every 30 seconds, so most events are saved
- For critical events, call `pulse.flush()` explicitly

**Q: How do I back up my data?**
- Copy `~/.pulse/data/events/` to a safe location
- Or set `--data-dir` to a cloud-synced folder

## Tech Stack

- **Backend**: Python, FastAPI, uvicorn
- **Storage**: Parquet files on disk, DuckDB for queries
- **Dashboard**: React, prebuilt and served as static files
- **SDKs**: Python and JavaScript/TypeScript

## License

MIT

## Support

- 📖 [Full documentation](https://github.com/rishita-khetan/pulse)
- 🐛 [Report issues](https://github.com/rishita-khetan/pulse/issues)
- 💬 [Discussions](https://github.com/rishita-khetan/pulse/discussions)
