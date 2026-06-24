# Headroom Dashboard

Desktop GUI for managing [Headroom](https://github.com/coder/headroom) — the context optimization proxy for Claude Code and other LLM tools.

One file. Double-click to run. Dependencies install themselves.

## Quick Start

**Requirements:** Python 3.9+

```
python headroom_app.py
```

First launch automatically installs `customtkinter`, `pystray`, and `Pillow`. Then go to the **Setup** tab and click **Install** next to `headroom-ai` to install the proxy engine.

## Platform Support

| OS | GUI App | CLI Scripts |
|----|---------|-------------|
| Windows | Full support | `headroom.ps1` / `headroom.bat` |
| macOS | Full support | — |
| Linux | Full support | — |

**Config location:**
| OS | Path |
|----|------|
| Windows | `%APPDATA%\headroom-app\config.json` |
| macOS | `~/Library/Application Support/headroom-app/config.json` |
| Linux | `~/.config/headroom-app/config.json` |

## Features

**Proxy Control**
- Toggle proxy on/off with a switch
- Auto-detects headroom from PATH, pip Scripts, or `HEADROOM_EXE` env var
- Sets `ANTHROPIC_BASE_URL` automatically so Claude Code routes through the proxy

**Live Dashboard** (auto-refreshes every 3s)
- Subscription usage — 5-hour / 7-day progress bars with reset timers
- Token savings, savings rate, cost saved at a glance
- Tabs: Requests, Performance, Tokens, Lifetime, Window tokens breakdown

**Configuration**
- Toggle proxy features: Code-Aware, Code-Graph, Memory, Learn, Optimize, Cache, Rate Limit, Kompress
- Apply & Restart button when proxy is running

**Rate Limit Alert**
- Warning bar when 5-hour usage exceeds 80%
- Tray notification if the app is minimized

**System Tray**
- Closing the window minimizes to tray (keeps monitoring)
- Right-click tray icon: Show / Quit

**Setup Tab**
- One-click install for all dependencies
- Status indicator for each package

## Files

| File | Purpose |
|------|---------|
| `headroom_app.py` | The app — only file needed to run |
| `headroom.ps1` | PowerShell CLI wrapper (Windows, optional) |
| `headroom.bat` | Batch CLI wrapper (Windows, optional) |

## How It Works

The app talks to the Headroom proxy's HTTP API:
- `GET /health` — proxy status, version, service checks, config
- `GET /stats` — token savings, cost, requests, subscription usage, performance

The proxy sits between Claude Code and the Anthropic API, compressing context to reduce token usage and cost.
