# Pulse Analytics

A plug-and-play local analytics dashboard for developers. Run one command, get instant insights into your app's events. No Docker, no cloud accounts, no setup.

```bash
pulse start
```

That's it. Your analytics dashboard opens at `http://localhost:4747`.

## Features

- **📊 Event tracking** - Track any event in your app (page views, button clicks, signups, errors, etc.)
- **🎯 Live dashboard** - Counts, trends, top users and recent events
- **🔗 Funnel analysis** - See where users drop off, plus auto-suggested funnels from your data
- **📈 Retention** - See how many users come back on later days
- **🧪 A/B testing** - Deterministic variant assignment with a significance test
- **⚡ Fast & local** - All data stays on your machine, stored as Parquet files and queried with DuckDB
- **🐍 Python & JS SDKs** - Track events from any backend or frontend

## Installation

Pulse is not on PyPI yet, so install it from the source code:

```bash
git clone https://github.com/RishitaKhetan/pulse.git
cd pulse
pip install -e .
```

Requires Python 3.10+.

## Quick Start (3 steps)

### 1. Start Pulse

```bash
pulse start
```

The dashboard opens at `http://localhost:4747`. Keep this terminal open; stop Pulse with `Ctrl+C`.

### 2. Add the SDK to your app

#### JavaScript (any website)

```html
<script src="http://localhost:4747/pulse.js"></script>
<script>
  Pulse.init();               // also records a page_view automatically
  Pulse.identify("alice");    // who the current user is (optional)

  // Track an event: Pulse.track(event_name, properties)
  Pulse.track("button_click", { button: "signup" });
</script>
```

#### Python (any backend or script)

```python
import pulse

pulse.init()  # call once at startup

# Track an event: pulse.track(event_name, user_id=..., properties=...)
pulse.track("signup", user_id="alice", properties={"plan": "pro"})
```

### 3. Look at the dashboard

Refresh `http://localhost:4747`. Your events appear in the charts.

No app yet? Fill the dashboard with sample data:

```bash
pulse demo-data
```

## How sending works

You don't need to do anything special. The SDKs collect events and send them in small batches so your app stays fast:

| | Sends a batch when... | Also sends when... |
|---|---|---|
| **JavaScript** | 10 events are waiting, or 3 seconds after an event | the tab is hidden or closed |
| **Python** | 100 events are waiting, or every 5 seconds | your program exits |

Call `Pulse.flush()` / `pulse.flush()` to send right away. The SDKs never crash your app. If Pulse isn't running, the JS SDK drops that batch; the Python SDK keeps up to 10,000 events and retries until Pulse is back.

The server keeps incoming events in memory and saves them to disk every 30 seconds, and whenever the dashboard asks for data.

## JavaScript SDK reference

| Call | What it does |
|---|---|
| `Pulse.init({ endpoint, userId, autoTrack })` | Start the SDK. All options are optional: `endpoint` defaults to `http://localhost:4747`, `autoTrack: false` turns off automatic `page_view` events. |
| `Pulse.identify(userId)` | Set the user for all following events. |
| `Pulse.track(eventName, properties)` | Record an event. The page URL and referrer are added to `properties` automatically. |
| `Pulse.experiment(name, userId)` | Returns a Promise with the user's variant, e.g. `"control"` (or `null` if Pulse is unreachable). |
| `Pulse.flush()` | Send waiting events now. |

## Python SDK reference

| Call | What it does |
|---|---|
| `pulse.init(endpoint="http://localhost:4747")` | Start the SDK. |
| `pulse.track(event_name, user_id=None, properties=None)` | Record an event. |
| `pulse.experiment(name, user_id)` | Returns the user's variant, e.g. `"control"` (or `None` if Pulse is unreachable). |
| `pulse.flush()` | Send waiting events now. |

## Event format

Every event has these fields. Only `event_name` is required; Pulse fills in the rest.

| Field | Meaning | Example |
|---|---|---|
| `event_name` | What happened | `"page_view"` |
| `user_id` | Who did it | `"alice"` |
| `session_id` | Which visit it belongs to (SDKs set this) | `"e81b26ba-..."` |
| `timestamp` | When it happened, ISO format (defaults to now) | `"2026-11-03T15:30:45Z"` |
| `properties` | Any extra details, as a JSON object | `{"page": "/home"}` |

You can also send events without an SDK:

```bash
curl -X POST http://localhost:4747/events/batch \
  -H "Content-Type: application/json" \
  -d '[{"event_name": "page_view", "user_id": "alice", "properties": {"page": "/home"}}]'
```

If some events in a batch are broken, the good ones are still saved and the response tells you which ones were rejected and why:

```json
{"received": 1, "rejected": [{"index": 1, "error": "event_name: Field required"}]}
```

## A/B testing

**1. Create an experiment** (name, variants, and the event that counts as success):

```bash
curl -X POST http://localhost:4747/experiments \
  -H "Content-Type: application/json" \
  -d '{"name": "signup_button", "variants": ["blue", "red"], "goal_event": "signup"}'
```

**2. Ask which variant a user gets.** The same user always gets the same variant:

```python
variant = pulse.experiment("signup_button", user_id="alice")   # "blue" or "red"
```

```javascript
const variant = await Pulse.experiment("signup_button", "alice");
```

**3. Track the goal event as usual.** Pulse links it to the variant for you:

```python
pulse.track("signup", user_id="alice")
```

**4. See the results** in the dashboard's Experiments card, or at `GET /experiments/signup_button/results`. You get:

- per variant: users, conversions and conversion rate (the first variant is the "control")
- for every other variant: the difference from control plus a **95% confidence range** (bootstrap, 2,000 replays)
- a **plain-English summary**, for example:
  > red converts better than blue: 12.0% vs 10.0% (+2.0 points). We're 95% sure the real difference is between +1.6 points and +2.4 points.
- the `winner`, only when the whole range is above (or below) zero, and nothing is declared while any variant has fewer than 30 users
- the classic `p_value` (two variants only), for those who want it

## CLI commands

```bash
pulse start [--port 4747] [--no-browser] [--data-dir PATH]   # start the dashboard server
pulse init        # create a config file with default settings
pulse demo-data   # add 100 sample events
pulse reset       # delete all events AND experiments in the data folder
```

## Configuration

`pulse init` creates `~/.pulse/config.json` (on Windows: `C:\Users\<you>\.pulse\config.json`):

```json
{
  "data_dir": "C:\\Users\\<you>\\.pulse\\data\\events",
  "port": 4747,
  "open_browser": true
}
```

Command-line flags (like `--port`) win over the config file.

## Where your data lives

Everything is in the data folder (default `~/.pulse/data/events/`). Each day gets its own folder of Parquet files:

```
~/.pulse/data/events/
  experiments.json
  2026-11-03/
    09_1793671959_378d72e37a9748a88a5a4edb2f54e884.parquet
    09_1793671989_efd2608c06ba466192536fc67a69fe07.parquet
  2026-11-04/
    ...
```

To back up, copy the folder. To start fresh, run `pulse reset`.

## Privacy and security

- Pulse only listens on `127.0.0.1`, so other computers can't reach it.
- Any website can **send** events to Pulse (that's how the JS SDK works), but only the dashboard can **read** your data.

## Performance

Measured on 1 million local events:

- Event counts: about 0.05 seconds
- Funnel: about 0.2 to 0.5 seconds
- Funnel suggestions: about 0.4 seconds
- Experiment report (100,000 users, with statistics): about 0.2 seconds

SDK cost: one `pulse.track()` / `Pulse.track()` takes a few microseconds; on an app doing about 2 ms of work per request, the overhead stays under 2%.

Small files are merged into one file per day automatically, so queries stay fast over time.

Re-run the measurements yourself:

```bash
python benchmarks/experiment_report.py
python benchmarks/sdk_overhead.py
node benchmarks/sdk_overhead_js.js
```

## Troubleshooting

**The dashboard won't open**
- Port 4747 may be in use. Try `pulse start --port 5000` and open `http://localhost:5000`.

**Events aren't showing up**
- Check that `pulse start` is still running.
- JS: open the browser console (F12) and look for errors. Make sure `pulse.js` loaded.
- Python: call `pulse.init()` before `pulse.track(...)`.
- Wait a few seconds or call `flush()`, then refresh the dashboard.
- Send a test event with the `curl` command above. If it shows up, Pulse works and the problem is in your app's tracking code.

**My app crashed. Did I lose events?**
- Events still waiting in the SDK (a few seconds' worth) can be lost if the whole program crashes. Call `flush()` after important events like purchases.

## Tech stack

- **Backend**: Python, FastAPI, uvicorn
- **Storage**: Parquet files on disk (pyarrow), queried with DuckDB
- **Dashboard**: a single HTML page with Chart.js, served by Pulse itself
- **SDKs**: Python and JavaScript

## License

MIT
