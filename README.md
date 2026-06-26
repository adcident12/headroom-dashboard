# Headroom Dashboard

Desktop GUI for managing [Headroom](https://headroom-docs.vercel.app) — the context optimization proxy for Claude Code.

> **Note:** รองรับเฉพาะ **Claude** — ไม่รองรับ OpenAI, Gemini หรือ provider อื่น
>
> **รองรับ 2 รูปแบบ:**
> - **Claude Pro/Max subscription** — ใช้ผ่าน Claude Code ได้เลย ไม่ต้องตั้ง API key ใดๆ Claude Code จัดการ authentication ผ่าน subscription ให้เอง headroom proxy จะ pass-through ไปตามปกติ
> - **Anthropic API key** — สำหรับผู้ที่ใช้ API โดยตรง (ไม่ได้ใช้ subscription) ต้องตั้ง environment variable `ANTHROPIC_API_KEY` **ก่อนเปิด proxy** โดยรันคำสั่งใน terminal:
>   - Windows (Command Prompt / PowerShell): `setx ANTHROPIC_API_KEY "sk-ant-xxxxx"` แล้ว **ปิดและเปิด terminal ใหม่** เพื่อให้ env var มีผล
>   - macOS/Linux: เพิ่ม `export ANTHROPIC_API_KEY="sk-ant-xxxxx"` ใน `~/.bashrc` หรือ `~/.zshrc` แล้วเปิด terminal ใหม่
>
> **ผู้ใช้ Claude Code CLI:** หากใช้ Claude Code ผ่าน subscription อยู่แล้ว (เช่น `claude` command ใช้งานได้ปกติ) ไม่ต้องตั้ง `ANTHROPIC_API_KEY` — แค่เปิด proxy ใน Headroom Dashboard แล้วเปิด terminal ใหม่เพื่อรัน Claude Code ผ่าน proxy ได้ทันที

> **Disclaimer:** Repo นี้เป็นโปรเจกต์ส่วนตัวที่สร้างขึ้นเพื่อทดสอบและใช้งานเอง — **ไม่มีแผน patch หรืออัปเดตตาม Headroom อย่างต่อเนื่อง** หาก Headroom API เปลี่ยน dashboard อาจแสดงผลไม่ถูกต้อง ยินดีแชร์ให้นำไปใช้และพัฒนาต่อได้อิสระ (fork ได้เลย) แต่ไม่รับประกันการ maintain ระยะยาว

Single file. Double-click to run. Dependencies install themselves.

![Dashboard](screenshots/dashboard.png)

---

## Table of Contents

- [Quick Start](#quick-start)
- [UI Overview](#ui-overview)
- [Tabs Reference](#tabs-reference)
- [Configuration](#configuration)
- [Setup Tab](#setup-tab)
- [Rate Limit Alert](#rate-limit-alert)
- [System Tray](#system-tray)
- [Architecture](#architecture)
- [Build Standalone Executable](#build-standalone-executable)
- [Developer Guide](#developer-guide)
- [Platform Support](#platform-support)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### Prerequisites

| ซอฟต์แวร์ | เวอร์ชันขั้นต่ำ | หมายเหตุ |
|-----------|---------------|---------|
| **Python** | 3.9+ | ต้องติดตั้งก่อนใช้งาน |
| **C/C++ Compiler** | — | **ต้องติดตั้งก่อน** — ใช้ compile Rust linker และ C++ extensions (ดูรายละเอียดด้านล่าง) |
| **Rust** | 1.88+ | ใช้ build headroom-ai (app ติดตั้งให้อัตโนมัติ) |
| **tkinter** | — | มาพร้อม Python บน Windows/macOS; Linux ต้อง `apt install python3-tk` |

<details>
<summary>วิธีติดตั้ง Python (คลิกเพื่อดู)</summary>

**Windows:**
1. ดาวน์โหลดจาก https://www.python.org/downloads/
2. ติ๊ก ☑ **"Add Python to PATH"** ตอน install
3. เปิด terminal ใหม่ ทดสอบ: `python --version`

> ถ้าเจอ "Python was not found" — ไปที่ Settings > Apps > Advanced app settings > App execution aliases แล้ว**ปิด** "App Installer python.exe" และ "App Installer python3.exe"

**macOS:**
```bash
brew install python
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install python3 python3-pip python3-tk
```

**Linux (Fedora):**
```bash
sudo dnf install python3 python3-pip python3-tkinter
```
</details>

<details>
<summary>C/C++ Compiler — จำเป็นสำหรับ build headroom-ai และ dependencies (คลิกเพื่อดู)</summary>

`headroom-ai` มี Rust component ที่ต้อง compile ด้วย `maturin` และ dependency `hnswlib` เป็น C++ extension — ทั้งคู่ต้องการ C/C++ compiler บนเครื่อง ถ้าไม่มีจะเจอ error:

```
error: linker `link.exe` not found
error: Microsoft Visual C++ 14.0 or greater is required.
```

**Windows — Microsoft Visual C++ Build Tools:**

1. ดาวน์โหลดจาก https://visualstudio.microsoft.com/visual-cpp-build-tools/
2. เลือก workload **"Desktop development with C++"**
3. ตรวจสอบว่าเลือก component: **MSVC v14x** และ **Windows SDK**
4. กด Install แล้ว restart terminal

![Visual Studio Build Tools](screenshots/microsoft_visual_C++_build_tools.png)

**macOS — Xcode Command Line Tools:**

```bash
xcode-select --install
```

ไม่ต้องติดตั้ง Xcode เต็ม — Command Line Tools มี `clang` ที่เพียงพอ

**Linux (Ubuntu/Debian):**

```bash
sudo apt install build-essential python3-dev
```

**Linux (Fedora/RHEL):**

```bash
sudo dnf groupinstall "Development Tools"
sudo dnf install python3-devel
```

**Linux (Arch):**

```bash
sudo pacman -S base-devel
```

</details>

### Step 1 — Run

```bash
python headroom_app.py
```

ครั้งแรกจะเปิดหน้าต่าง bootstrap ติดตั้ง `customtkinter`, `pystray`, `Pillow` อัตโนมัติ แล้ว restart เข้า app หลัก

### Step 2 — Setup Everything

App จะสลับไปหน้า **Setup** อัตโนมัติ กดปุ่ม **Setup Everything** เพื่อ:

1. ตรวจสอบ/ติดตั้ง/อัปเดต **Rust Compiler** (ต้องการ v1.88+)
2. ติดตั้ง **headroom-ai[all]** และ dependencies ทั้งหมด

ระหว่างติดตั้งจะแสดง progress bar และ terminal log แบบ real-time

<details>
<summary>ติดตั้ง manual ผ่าน terminal</summary>

```bash
# ติดตั้ง/อัปเดต Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh   # Linux/macOS
# หรือ https://win.rustup.rs/x86_64 สำหรับ Windows

rustup update stable

# ติดตั้ง headroom
pip install "headroom-ai[all]"
```
</details>

### Step 3 — เปิด Proxy

กด **switch Proxy** ใน sidebar เป็น ON — app จะ:

1. เปิด headroom proxy บน `http://127.0.0.1:8787`
2. ตั้ง `ANTHROPIC_BASE_URL` ให้อัตโนมัติ (persist ข้าม session)
3. Claude Code session ใหม่จะ route ผ่าน Headroom ทันที

> **Windows:** หลังเปิดหรือปิด proxy ต้อง **ปิดแล้วเปิด VS Code / terminal ใหม่** เพื่อรับ env var ล่าสุด (ไม่ต้อง log out/log in)
> macOS/Linux: เปิด terminal ใหม่ก็พอ

---

## UI Overview

App แบ่งเป็น 2 ส่วน: **Sidebar** (ซ้าย) และ **Main Dashboard** (ขวา)

### Sidebar

| ส่วน | รายละเอียด |
|------|-----------|
| **Proxy Switch** | เปิด/ปิด proxy — set env var + start/stop process (disabled ระหว่างดำเนินการป้องกันกดซ้ำ) |
| **Hint Label** | (Windows) แสดงคำแนะนำให้ restart VS Code / terminal หลังเปิด/ปิด proxy |
| **Version / Uptime** | เวอร์ชัน proxy และเวลาที่ทำงานมา |
| **Services** | สถานะ internal services — `●` เขียว = healthy, `○` เทา = disabled, `●` แดง = error |
| **Timestamp** | เวลาล่าสุดที่ refresh ข้อมูล |

### Usage Bars (Progress Bars)

แสดง subscription usage ของ Anthropic API:

| Bar | ความหมาย |
|-----|---------|
| **5-hour** | การใช้งานใน 5 ชั่วโมงล่าสุด — เกิน limit ต้องรอ reset |
| **7-day** | การใช้งานรวม 7 วัน |
| **Extra** | extra usage (ถ้าเปิด) — แสดงยอดเงิน / limit |

สีของ bar: **เขียว** (<60%) → **เหลือง** (60-80%) → **แดง** (>80% + alert)

### Hero Stats

ตัวเลขใหญ่ 3 ตัวตรงกลาง:

| Stat | ความหมาย |
|------|---------|
| **tokens saved** | จำนวน token ที่ลดได้ (เช่น 3.2M = 3.2 ล้าน tokens) |
| **savings rate** | เปอร์เซ็นต์ที่ลด (เช่น 40.1% = ทุก 100 tokens ลดได้ 40) |
| **cost saved** | เงินที่ประหยัดได้ (คำนวณจาก token price) |

---

## Tabs Reference

### Requests

| Field | Source | ความหมาย |
|-------|--------|---------|
| Total | `stats.requests.total` | จำนวน request ทั้งหมดที่ผ่าน proxy |
| Cached | `stats.requests.cached` | request ที่ตอบจาก cache |
| Rate limited | `stats.requests.rate_limited` | request ที่ถูก rate limit |
| Failed | `stats.requests.failed` | request ที่ล้มเหลว |

### Performance (two-column)

| Column | Field | Source | ความหมาย |
|--------|-------|--------|---------|
| **LATENCY** | TTFB avg | `stats.ttfb.average_ms` | Time to First Byte เฉลี่ย |
| | TTFB range | `stats.ttfb.min_ms` – `max_ms` | ช่วง min-max ของ TTFB |
| | Overhead | `stats.overhead.average_ms` | เวลาที่ proxy เพิ่มเข้ามา |
| | Latency | `stats.latency.average_ms` | latency รวมทั้งหมด |
| **THROUGHPUT** | Gen p50 | `stats.throughput.rolling.generation_p50` | output generation speed (tok/s) |
| | Gen p95 | `stats.throughput.rolling.generation_p95` | p95 ของ generation speed |
| | Comp p50 | `stats.throughput.rolling.compression_p50` | compression speed (tok/s) |
| | Comp p95 | `stats.throughput.rolling.compression_p95` | p95 ของ compression speed |

### Savings

| Section | Field | Source | ความหมาย |
|---------|-------|--------|---------|
| **Tokens** | Input | `stats.tokens.input` | input tokens ทั้งหมด |
| | Output | `stats.tokens.output` | output tokens ทั้งหมด |
| | Saved | `stats.tokens.all_layers_saved` | tokens ที่ลดได้ |
| | Compression | `stats.tokens.proxy_compression_saved` | จาก compression |
| | CLI filtering | `stats.tokens.cli_filtering_saved` | จาก CLI filtering |
| **Cost** | Without proxy | `cost_with_headroom_usd + savings_usd` | ค่าใช้จ่ายถ้าไม่มี proxy (คำนวณ) |
| | With proxy | `stats.cost.cost_with_headroom_usd` | ค่าใช้จ่ายจริงผ่าน proxy |
| | Cache savings | `stats.cost.cache_savings_usd` | เงินที่ประหยัดจาก caching |

### History (two-column)

| Column | Section | Field | Source |
|--------|---------|-------|--------|
| **Left** | SESSION | Requests | `stats.display_session.requests` |
| | | Saved | `stats.display_session.tokens_saved` |
| | ALL TIME | Requests | `stats.persistent_savings.lifetime.requests` |
| | | Tokens saved | `stats.persistent_savings.lifetime.tokens_saved` |
| | | Savings | `stats.persistent_savings.lifetime.compression_savings_usd` |
| **Right** | WINDOW | Input | `stats.subscription_window.window_tokens.input` |
| | | Output | `stats.subscription_window.window_tokens.output` |
| | | Cache reads | `stats.subscription_window.window_tokens.cache_reads` |
| | | Total | `stats.subscription_window.window_tokens.total_raw` |
| | EFFICIENCY | Rate | `stats.subscription_window.contribution.efficiency_pct` |

Model breakdown แสดงด้านล่าง แยกตาม model ที่ใช้

### Agents

| Field | Source | ความหมาย |
|-------|--------|---------|
| Total requests | `stats.agent_usage.totals.requests` | request ทั้งหมดจากทุก agent |
| Tokens saved | `stats.agent_usage.totals.tokens_saved` | tokens ที่ลดได้รวม |
| Savings rate | `stats.agent_usage.totals.savings_percent` | อัตราการลดรวม |

ด้านล่างเป็น scrollable list แสดง per-agent: ชื่อ agent, จำนวน requests, tokens saved

### Config

ดูหัวข้อ [Configuration](#configuration)

### Setup

ดูหัวข้อ [Setup Tab](#setup-tab)

---

## Configuration

ใน **Config** tab เปิด/ปิด features ของ proxy:

| Feature | Default | ทำอะไร |
|---------|---------|--------|
| **Code-Aware** | ON | ใช้ AST ในการ compress code — เข้าใจโครงสร้างภาษา |
| **Code-Graph** | OFF | Index codebase ทั้งโปรเจกต์ เพื่อให้ compression ฉลาดขึ้น |
| **Memory** | OFF | จำ context ข้าม session (SQLite local / Qdrant) |
| **Learn** | OFF | เรียนรู้จาก error patterns (ต้องเปิด Memory ด้วย) |
| **Optimize** | ON | เปิด compression หลัก — ปิดจะเป็น passthrough mode |
| **Cache** | ON | Semantic caching — request ซ้ำจะตอบจาก cache |
| **Rate Limit** | ON | ป้องกัน rate limit จาก API provider |
| **Kompress** | ON | ML-based compression engine |

เมื่อเปลี่ยนค่า:
- บันทึกอัตโนมัติลง config file
- ถ้า proxy ทำงานอยู่ → ปุ่ม **Apply & Restart** สีเหลือง → กดเพื่อ restart
- ถ้า proxy ปิดอยู่ → เปิดครั้งหน้าจะใช้ settings ใหม่

---

## Setup Tab

### System Tools

| Tool | ความต้องการ | ทำอะไร |
|------|------------|--------|
| **Rust Compiler** | v1.88+ | ใช้ build headroom-ai จาก source |

แสดงสถานะ: version ที่ตรวจพบ, ปุ่ม Install/Update ถ้าจำเป็น

### Python Packages

| Package | ทำไมต้องมี |
|---------|-----------|
| **headroom-ai[all]** | Proxy engine + ทุก feature |
| **customtkinter** | UI framework |
| **pystray** | ย่อลง system tray |
| **Pillow** | สร้าง icon สำหรับ tray |

แสดงสถานะ: `●` เขียว = ติดตั้งแล้ว, `○` แดง = ยังไม่มี

### ปุ่ม Setup Everything

กดครั้งเดียว ติดตั้ง/อัปเดตทุกอย่างที่ขาดตามลำดับ: Rust → Python packages
พร้อม progress bar และ terminal log แบบ real-time

### Bundled Tools (หลังติดตั้ง headroom-ai)

| Tool | ทำอะไร | ติดตั้งเพิ่ม |
|------|--------|-------------|
| **ast-grep** | AST-aware structural search | มากับ pip |
| **difft** | Structural diff | `headroom tools install` |
| **scc** | Lines-of-code analysis | `headroom tools install` |

---

## Rate Limit Alert

เมื่อ 5-hour usage เกิน 80%:

1. **Alert bar สีแดง** ด้านบน dashboard — แสดง % และเวลา reset
2. **Tray notification** (ถ้าย่อลง tray) — เตือนครั้งเดียวต่อรอบ
3. **Progress bar สีแดง** ใน Usage section

เมื่อ usage ลงต่ำกว่า 80% → alert หายไปอัตโนมัติ

---

## System Tray

- กด **X** (ปิดหน้าต่าง) → ย่อลง tray ไม่ใช่ปิด app — proxy ยังทำงาน
- **Tray icon สีตามสถานะ proxy:**
  -  **เขียว** — proxy เปิดอยู่ (ON)
  -  **แดง** — proxy ปิดอยู่ (OFF)
  - Icon อัปเดตสีอัตโนมัติทุก 3 วินาทีตามสถานะจริง
- ย่อลง tray จะแสดง **notification** พร้อมไอคอน Headroom สีตามสถานะ:
  - Proxy ON: "Headroom is running — proxy is ON."
  - Proxy OFF: "Headroom is running — proxy is OFF."
  - (Windows: ใช้ Windows Toast Notification พร้อมไอคอนกำหนดเอง แทน Python default icon)
- **Double-click** tray icon → เปิดหน้าต่างกลับ
- **คลิกขวา** → Show / Quit
- ถ้าไม่มี `pystray` + `Pillow` → กด X จะปิด app ปกติ

### Single Instance

App ป้องกันการเปิดซ้ำ — ถ้าเปิด `headroom_app.py` ขณะที่มี instance ทำงานอยู่แล้ว (รวมถึงที่ย่อลง tray) จะแสดง dialog "Headroom is already running. Check the system tray." แทนการเปิด instance ใหม่

| OS | กลไก |
|----|------|
| Windows | Named Mutex (`Global\HeadroomAppMutex`) |
| macOS / Linux | File lock (`fcntl.flock`) |

---

## Architecture

### System Diagram

```
Claude Code  ──►  Headroom Proxy (localhost:8787)  ──►  Anthropic API
                         │
                    compress context
                    cache responses
                    track usage
                         │
                  Headroom Dashboard  ◄── GET /health
                    (this app)        ◄── GET /stats  (every 3s)
```

### Data Flow

1. **Headroom Proxy** รับ request จาก Claude Code → compress context → ส่งไป Anthropic API
2. **Dashboard** poll proxy ผ่าน HTTP ทุก 3 วินาที:
   - `GET /health` — สถานะ, version, services, config
   - `GET /stats` — tokens, cost, requests, subscription, performance, agents
3. **Environment variable** `ANTHROPIC_BASE_URL=http://127.0.0.1:8787` ทำให้ Claude Code route ผ่าน proxy

---

## Developer Guide

### Project Structure

```
headroom-dashboard/
├── headroom_app.py      # ตัว app ทั้งหมด (single file)
├── build.py             # PyInstaller build script
├── requirements.txt     # Python dependencies
├── headroom.ico         # App icon (Windows build)
├── headroom.png         # App icon source (256x256)
├── README.md
└── screenshots/
```

ออกแบบเป็น **single-file app** — ไม่ต้อง setup project, ไม่มี build step, copy ไฟล์เดียวแล้วรันได้

### Code Architecture

```
headroom_app.py
├── _bootstrap()                    # auto-install customtkinter, pystray, Pillow
├── _acquire_instance_lock()        # Named Mutex (Windows) / fcntl (Unix)
├── Helpers
│   ├── _find_headroom_exe()        # locate headroom binary
│   ├── _get_appdata()              # OS-specific appdata directory
│   ├── fetch_json(path)            # HTTP GET from proxy (1MB cap, 2s timeout)
│   ├── deep(d, *keys)              # safe nested dict access
│   ├── fmt_tokens / fmt_usd / fmt_rate / fmt_duration
│   ├── load_config / save_config   # JSON config (atomic write via os.replace)
│   ├── save_pid / load_pid / clear_pid
│   └── build_proxy_args(cfg)       # construct proxy CLI arguments
├── Platform Helpers
│   ├── _popen_kwargs()             # CREATE_NO_WINDOW on Windows
│   ├── _is_headroom_process(pid)   # verify PID via CommandLine (Win: Get-CimInstance, macOS: ps, Linux: /proc)
│   ├── _kill_pid(pid)              # kill by PID with safety check
│   ├── _kill_by_name()             # kill by process name (fallback)
│   ├── _broadcast_env_change()     # WM_SETTINGCHANGE broadcast (Windows)
│   ├── _set_env_persistent()       # set env var (winreg / shell rc)
│   ├── _unset_env_persistent()     # remove env var
│   ├── _shell_rc_files()           # platform-aware list of shell rc files
│   ├── _write_shell_export()       # append export to rc files (escaped, with ~/.profile fallback)
│   ├── _xml_escape()               # escape XML special chars for toast notifications
│   ├── _notify_toast()             # Windows Toast Notification with custom icon
│   ├── _remove_shell_export()      # remove export + comment from bashrc/zshrc
│   └── _open_in_explorer()         # open file in OS file manager
└── HeadroomApp (CTk)
    ├── __init__                    # window setup, build UI
    ├── _build_sidebar()            # proxy switch, hint label, version, services
    ├── _build_main()               # usage bars, hero stats, tabs
    │   ├── Requests tab
    │   ├── Performance tab         # two-column: Latency + Throughput
    │   ├── Savings tab             # tokens + cost breakdown
    │   ├── History tab             # Session/Lifetime + Window/Efficiency
    │   ├── Agents tab              # totals + scrollable per-agent list
    │   ├── Config tab              # proxy feature switches + restart
    │   └── Setup tab               # Rust + Python deps + Install All
    ├── _build_alert_bar()          # rate limit alert overlay
    ├── Lifecycle
    │   ├── _on_close()             # window close → cleanup + destroy
    │   ├── _cleanup_env()          # remove stale env vars (if proxy stopped)
    │   ├── _cleanup_tray()         # stop tray icon
    │   ├── _minimize_to_tray()     # X button → tray + notification
    │   └── _tray_quit()            # tray menu → cleanup + destroy
    ├── Proxy Control (_proxy_lock guards all)
    │   ├── _on_switch()            # toggle handler (thread-safe via _proxy_lock)
    │   ├── _do_start()             # start proxy (daemon thread)
    │   ├── _do_stop()              # stop proxy
    │   ├── _stop_proxy_process()   # kill proxy by PID
    │   ├── _restart_proxy()        # config change → restart
    │   └── _do_restart()           # stop + start in sequence
    ├── Refresh Cycle (every 3s)
    │   ├── _refresh()              # spawn fetch thread
    │   ├── _fetch_and_apply()      # HTTP fetch (background thread)
    │   └── _apply_data()           # update all widgets (main thread)
    ├── Update Methods
    │   ├── _update_sidebar()       # version, uptime, services
    │   ├── _update_usage()         # subscription window bars
    │   ├── _update_hero()          # 3 hero stats
    │   ├── _update_requests()      # request counters + by_model
    │   ├── _update_performance()   # latency, TTFB, overhead
    │   ├── _update_throughput()    # generation / compression tok/s
    │   ├── _update_tokens()        # token breakdown
    │   ├── _update_cost()          # with/without proxy + cache savings
    │   ├── _update_lifetime()      # lifetime + session stats
    │   ├── _update_window_tokens() # subscription window token detail
    │   ├── _update_contribution()  # headroom contribution to window
    │   ├── _update_agents()        # per-agent breakdown
    │   ├── _update_alert()         # rate limit warning bar
    │   └── _update_config()        # sync config checkboxes from health
    └── Install System
        ├── _first_run_check()      # auto-open setup tab if deps missing
        ├── _check_deps()           # scan installed packages + Rust
        ├── _detect_rust()          # find rustc, check version
        ├── _install_rust()         # download + install via rustup-init
        ├── _update_rust()          # rustup update stable
        ├── _install_package(pkg)   # pip install single package
        ├── _install_all()          # install everything missing
        └── _run_stream(cmd)        # subprocess with real-time log output
```

### Key Patterns

**Widget Creation — `_detail_row()`:**
```python
# Creates left-aligned label + right-aligned bold value, returns value widget
val = self._detail_row(parent_frame, "Label", row_number)
# Later: val.configure(text="new value")
```

**Safe Data Access — `deep()`:**
```python
# Traverse nested dict safely, return fallback if any key is missing
wt = deep(stats, "subscription_window", "window_tokens", fallback={})
```

**Refresh Cycle:**
```
_refresh() → spawn daemon thread
  └─ _fetch_and_apply() → fetch_json("/health") + fetch_json("/stats")
       └─ self.after(0, _apply_data) → update all widgets on main thread
            └─ _schedule_next_refresh() → self.after(3000, _refresh)
```

**Threading Rules:**
- UI updates **must** run on main thread via `self.after(0, callback)`
- HTTP fetches run on daemon threads to avoid UI freeze
- `_fetch_lock` prevents concurrent fetches
- `_headroom_exe_lock` protects global `HEADROOM_EXE` writes

### Adding a New Data Section

1. **Add widgets** in `_build_main()` using `_detail_row()` or custom widgets
2. **Add update method** `_update_xxx(self, stats)` — read data with `deep()`, format with `fmt_*()`, update widgets
3. **Wire into `_apply_data()`** — add `self._update_xxx(stats)` call
4. **Test** — run app, verify data populates from live proxy

### Adding a New Tab

```python
# In _build_main():
t_new = tabs.add("TabName")
t_new.grid_columnconfigure(1, weight=1)
self._new_field = self._detail_row(t_new, "Label", 0)

# Add update method:
def _update_new(self, stats):
    data = deep(stats, "path", "to", "data", fallback={})
    self._new_field.configure(text=fmt_tokens(data.get("key", 0)))

# Wire in _apply_data():
self._update_new(stats)
```

### Two-Column Layout Pattern

```python
t = tabs.add("TwoCol")
t.grid_columnconfigure((0, 1), weight=1)

left = ctk.CTkFrame(t, fg_color="transparent")
left.grid(row=0, column=0, sticky="nsew")
left.grid_columnconfigure(1, weight=1)
ctk.CTkLabel(left, text="HEADER", font=ctk.CTkFont(size=9), text_color=DIM)
self._left_val = self._detail_row(left, "Field", 1)

right = ctk.CTkFrame(t, fg_color="transparent")
right.grid(row=0, column=1, sticky="nsew")
right.grid_columnconfigure(1, weight=1)
# ... same pattern
```

### Security Notes

- Environment variables set via `winreg` (Windows) or shell rc files (Unix) — no subprocess shell injection
- `HEADROOM_EXE` global protected by `threading.Lock()`
- `_proxy_lock` protects `_busy` flag and `_proxy_proc` from race conditions across threads
- subprocess handles use context managers (`with Popen(...) as proc:`)
- File handles use `with open()` — no leaks
- `fetch_json()` reads max 1MB, 2s timeout, localhost only — redirect blocked via `_NoRedirect`, catches specific exceptions only
- Config values validated against known keys before use
- Config writes are atomic (`os.replace()`) to prevent corruption on crash
- Single instance lock prevents duplicate processes
- PID reuse protection — `_is_headroom_process()` verifies process CommandLine (not just process name) before killing
- Shell export values escaped against injection (`"`, `$`, `` ` ``, `\`)
- `_kill_pid()` catches `PermissionError` and `OSError` for robustness
- `_stop_proxy_process()` verifies process is actually dead (`os.kill(pid, 0)`) before skipping fallback
- Failed proxy start cleans up: kills leaked process + clears PID file
- Toast notification XML content escaped via `_xml_escape()` — prevents XML injection
- Proxy switch disabled during start/stop/restart — prevents race conditions from rapid toggling
- Stale env vars cleaned up on all exit paths (close, tray quit, no-tray fallback)
- Windows: `CREATE_NO_WINDOW` flag on all subprocess calls including `_run_stream()`
- Bootstrap re-exec uses absolute path to prevent working-directory confusion

### API Reference

Dashboard reads from two proxy endpoints:

**`GET /health`**
```json
{
  "status": "healthy",
  "version": "0.27.0",
  "uptime_seconds": 3661,
  "services": {"optimizer": "on", "cache": "on", ...},
  "config": {"code_aware": true, ...}
}
```

**`GET /stats`** (key paths used by dashboard)
```
stats.requests.{total, cached, rate_limited, failed}
stats.tokens.{input, output, all_layers_saved, proxy_compression_saved, cli_filtering_saved}
stats.cost.{cost_with_headroom_usd, savings_usd, cache_savings_usd}
stats.latency.{average_ms, total_requests}
stats.ttfb.{average_ms, min_ms, max_ms}
stats.overhead.{average_ms}
stats.throughput.rolling.{generation_p50, generation_p95, compression_p50, compression_p95}
stats.subscription_window.latest.{five_hour, seven_day, extra_usage}
stats.subscription_window.window_tokens.{input, output, cache_reads, total_raw, by_model}
stats.subscription_window.contribution.{efficiency_pct, savings_usd}
stats.agent_usage.{totals, agents[]}
stats.persistent_savings.lifetime.{requests, tokens_saved, compression_savings_usd}
stats.display_session.{requests, tokens_saved}
```

---

## Platform Support

| OS | รองรับ |
|----|--------|
| Windows | Full support |
| macOS | Full support |
| Linux | Full support (ต้องมี `python3-tk`) |

### Config File Location

| OS | Path |
|----|------|
| Windows | `%APPDATA%\headroom-app\config.json` |
| macOS | `~/Library/Application Support/headroom-app/config.json` |
| Linux | `~/.config/headroom-app/config.json` |

### Platform-Specific Behavior

| การทำงาน | Windows | macOS | Linux |
|---------|---------|-------|-------|
| Set env var | `winreg` (HKCU\Environment) + broadcast `WM_SETTINGCHANGE` | append to `~/.zshrc` / `~/.bashrc` / `~/.bash_profile` / `~/.zprofile` | append to `~/.bashrc` / `~/.zshrc` (fallback: `~/.profile`) |
| Verify proxy process | `Get-CimInstance Win32_Process` (ตรวจ CommandLine) | `ps -p PID -o command=` | `/proc/PID/cmdline` |
| Kill proxy | `taskkill /PID` | `os.kill` (SIGTERM → SIGKILL) | `os.kill` (SIGTERM → SIGKILL) |
| Toast notification | Windows Toast API + custom PNG icon | `pystray.notify()` (fallback) | `pystray.notify()` (fallback) |
| UI fonts | Segoe UI / Consolas | SF Pro / Menlo | sans-serif / Monospace |
| Open file | `explorer /select,` | `open -R` | `xdg-open` |
| Hide console | `CREATE_NO_WINDOW` flag | ไม่จำเป็น | ไม่จำเป็น |
| Install Rust | `rustup-init.exe -y` | `curl ... \| sh -s -- -y` | `curl ... \| sh -s -- -y` |
| Bootstrap restart | `subprocess.Popen` + `sys.exit` | `os.execv` | `os.execv` |
| Single instance | Named Mutex (`kernel32.CreateMutexW`) | `fcntl.flock` lock file | `fcntl.flock` lock file |
| Env broadcast | `SendMessageTimeoutW(WM_SETTINGCHANGE)` | ไม่จำเป็น | ไม่จำเป็น |

---

## Build Standalone Executable

สร้างไฟล์ .exe / .app / binary ที่เปิดได้เลยโดยไม่ต้องติดตั้ง Python

### วิธี Build

```bash
# ติดตั้ง dependencies (ครั้งแรก)
pip install -r requirements.txt

# Build
python build.py
```

Output อยู่ที่ `dist/`:

| OS | Output | ขนาดโดยประมาณ |
|----|--------|--------------|
| Windows | `dist/Headroom.exe` | ~28 MB |
| macOS | `dist/Headroom.app` | ~30 MB |
| Linux | `dist/Headroom` | ~25 MB |

### ข้อจำกัด

- **ต้อง build บน OS เดียวกับที่จะใช้** — ไม่สามารถ cross-compile ได้ (เช่น build .exe บน macOS ไม่ได้)
- macOS: ต้อง build บน macOS จริง
- Linux: ต้อง build บน Linux จริง
- ผู้ใช้ปลายทางยังต้องติดตั้ง `headroom-ai` แยก (proxy engine ไม่ได้ bundle มาด้วย)

---

## Files

| File | จำเป็น | รายละเอียด |
|------|--------|-----------|
| `headroom_app.py` | ใช่ | ตัว app ทั้งหมด — ไฟล์เดียวที่ต้องใช้ |
| `build.py` | ไม่ | Script สำหรับ build standalone executable |
| `requirements.txt` | ไม่ | Python dependencies |
| `headroom.ico` | ไม่ | App icon สำหรับ Windows build |
| `headroom.png` | ไม่ | App icon source (256x256) |
| `README.md` | ไม่ | เอกสารนี้ |

> **แจกจ่ายแบบง่าย:** copy แค่ `headroom_app.py` ไฟล์เดียว แล้ว `python headroom_app.py`
> **แจกจ่ายแบบ standalone:** build ด้วย `python build.py` แล้วแจก `dist/Headroom.exe`

---

## Troubleshooting

| ปัญหา | แก้ไข |
|-------|------|
| App เปิดแล้วเห็นแต่ "Setting up..." | รอ pip install เสร็จ ถ้า fail ดู error แล้วรัน `pip install customtkinter` เอง |
| Proxy เปิดแล้วแต่ Claude Code ไม่ผ่าน Headroom | ปิดแล้วเปิด VS Code / terminal ใหม่ เพื่อรับ env var ใหม่ |
| ปิด proxy แล้วเจอ `ConnectionRefused` | ปิดแล้วเปิด VS Code / terminal ใหม่ เพื่อเชื่อมต่อ API โดยตรง |
| `linker link.exe not found` หรือ `Microsoft Visual C++ 14.0 required` | ติดตั้ง [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) เลือก "Desktop development with C++" (ดู Prerequisites) |
| "headroom not found" ตอนกด ON | ไป Setup tab กด Setup Everything หรือ `pip install "headroom-ai[all]"` |
| Rust version เก่าเกินไป | ไป Setup tab กด Update ที่ Rust หรือรัน `rustup update stable` |
| Build headroom-ai ล้มเหลว | ตรวจว่า Rust >= 1.88: `rustc --version` ถ้าไม่ใช่ให้ `rustup update stable` |
| Dashboard แสดง 0 ทุกที่ | ยังไม่มี request ผ่าน proxy — ใช้ Claude Code แล้วข้อมูลจะขึ้น |
| Port 8787 ถูกใช้งาน | ปิด process ที่ใช้ port นั้น: Windows `netstat -ano \| findstr 8787` แล้ว `taskkill /F /PID <pid>`, Linux/macOS `lsof -i :8787` แล้ว `kill <pid>` |
| Linux: `tkinter` not found | `sudo apt install python3-tk` (Ubuntu) หรือ `sudo dnf install python3-tkinter` (Fedora) |
| Window tab แสดง — ทั้งหมด | ตรวจว่า proxy ทำงานอยู่และมี request ผ่านไปแล้วอย่างน้อย 1 ครั้ง |
| "Headroom is already running" | App เปิดอยู่แล้ว (อาจอยู่ใน system tray) — ดูที่ tray icon แล้ว double-click เพื่อเปิดหน้าต่าง |
