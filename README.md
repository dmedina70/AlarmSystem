# Alarm Monitor Server

A fullscreen alarm monitoring dashboard for SMT production lines. Displays line statuses as color-coded tiles, plays audio alerts on alarm triggers, replays unresolved alarms at configurable intervals, and sends webhook notifications.

## Features

- **Fullscreen tile grid** — each production line gets a large, color-coded tile (green = OK, red/custom = alarm active)
- **Audio alerts** — plays configurable WAV files per line/alarm combination
- **Auto-replay** — unresolved alarms re-trigger at a configurable interval
- **Elapsed timer** — each active alarm tile shows a running stopwatch
- **Webhook notifications** — posts alarm triggered/solved events to a webhook (e.g. Teams)
- **CSV logging** — all alarm events logged to `alarm_requests.csv`

## Requirements

- Python 3.8+
- `pygame` — audio playback
- `requests` — webhook notifications
- A display environment (Tkinter) for the GUI

```
pip install pygame requests
```

## Configuration Files

| File | Purpose |
|---|---|
| `config.init` | Server port, webhook URL, replay interval |
| `config_server.txt` | Maps `line, alarm_name, sound_file_path` (one per line) |
| `lines.txt` | Ordered list of line names to display (one per line) |
| `alarm_colors.txt` | Optional custom alarm colors (`alarm_name = #hex`) |

### `config.init` example

```ini
[Server]
port = 9999
hook = https://your-webhook-url

[Interval]
interval = 300
```

### `config_server.txt` example

```
Line1, Stencil, /path/to/sounds/stencil.wav
Line1, Feeder,  /path/to/sounds/feeder.wav
Line2, Stencil, /path/to/sounds/stencil.wav
```

### `lines.txt` example

```
Line1
Line2
Line3
```

### `alarm_colors.txt` example

```
Stencil = #ff6600
Feeder = #ffcc00
```

## Usage

```bash
python smt_alarm_server.py
```

The server starts in fullscreen mode. Press **Escape** to exit fullscreen or **F11** to toggle it.

## Client Protocol

The server listens for TCP connections on the configured port. Clients send JSON messages:

**Trigger an alarm:**
```json
{"line": "Line1", "alarm": "Stencil"}
```

**Solve an alarm:**
```json
{"line": "Line1", "alarm": "Stencil", "solved": true, "employee": "John", "elapsed": 45.2}
```

The server responds with `OK` on success or an `error:` prefixed message on failure.

## Output Files

- `alarm_requests.csv` — log of all alarm events (timestamp, line, alarm, status, employee, elapsed)
- `server_debug.log` — debug log
