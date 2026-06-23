# Network ZTP Registry — Technical Overview

**Zero Touch Provisioning for Cisco Catalyst 9000 Series**

---

## What It Does

When a new switch arrives and is plugged into the OpenGear console server, it self-provisions completely without manual console interaction. It receives an IP address, downloads and executes a Python configuration script, applies a base configuration, sets its hostname, and upgrades IOS-XE if the version doesn't match the target. The switch then appears in a web dashboard where a user records the asset tag, prints a label, and closes out the staging workflow.

The system eliminates manual console access for initial provisioning. Users interact only with a browser.

---

## System Topology

```
198.51.100.0/24 (user network)
      │
      │  https://198.51.100.14:8080  (OpenGear UI proxy)
      │  http://198.51.100.14:5000   (ZTP dashboard proxy)
      │
┌─────┴──────────────────────────────────┐
│  Linux Server  192.0.2.14          │
│                                        │
│  nginx (port 80)  — IOS images,        │
│                     config.json        │
│  nginx (port 8080) — HTTPS proxy       │
│                      → OpenGear UI     │
│  nginx (port 5000) — HTTP proxy        │
│                      → ZTP dashboard   │
│                                        │
│  Docker                                │
│  ├── registry  (Flask, port 5000)      │
│  └── poller    (Python daemon)         │
└─────────────────────────────────────────┘
             │  192.0.2.0/24 (ZTP subnet)
             │
┌────────────┴───────────────────────────┐
│  OpenGear CM8100  192.0.2.253      │
│                                        │
│  Console ports 2–8 ──────────────────┐ │
│  Ethernet ports 2–8 ─────────────────┤ │
│                                      │ │
│  Docker                              │ │
│  ├── registry  (Flask, port 5000)    │ │
│  └── poller    (Python daemon)       │ │
└──────────────────────────────────────┼─┘
                                       │
              ┌────────────────────────┘
              │  (up to 7 switches simultaneously)
         ┌────┴────┐
         │ Switch  │  Cisco Catalyst C9300/C9300X/C9410R/C9606R
         │         │  Console → OpenGear console port
         └─────────┘  GigE0/0 → OpenGear Ethernet port
```

---

## Tech Stack

### Python 3 — Core Language

All server-side logic is Python 3. Three distinct Python processes make up the system:

- **server.py** — Flask web application (registry API + dashboard)
- **opengear_poller.py** — polling daemon (no web framework; pure stdlib + requests)
- **ztp.py** — provisioning script that runs directly on the switch

### Flask — Web API and Dashboard

`server.py` is a Flask application that serves two roles simultaneously:

1. **REST API** — CRUD endpoints for device records, lookup by serial number, live session updates, Ansible playbook execution
2. **Static file host** — serves `static/index.html`, the browser dashboard

Flask was chosen for its minimal footprint. The entire API fits in one file with no ORM or abstraction layers. All database access is raw SQLite via Python's built-in `sqlite3` module.

Key Flask patterns used:
- **Server-Sent Events (SSE)** via a generator function and `text/event-stream` response — pushes real-time device table updates and live provisioning cards to the browser without polling
- **`after_request` hooks** — CORS headers injected on every response for development access
- **Shared in-memory state** (`_sse_clients` list) — tracks open SSE connections for fan-out

### SQLite — Device Registry

All device records live in a single SQLite database (`devices.db`) mounted into the Docker container via a named volume (`ztp-data`). Schema is a single `devices` table with columns for every field shown in the dashboard: hostname, model, serial, IP, IOS version, hardware inventory (JSON blob), building, floor, room, MTAG (`asset_tag`), notes, status, and timestamps.

SQLite was chosen deliberately: the write volume is low (one insert per switch provisioned, occasional updates), there is no concurrent write contention that SQLite can't handle, and zero infrastructure overhead compared to Postgres or MySQL.

### JSON File IPC — Poller ↔ Server State

The poller and server share state through a JSON file (`.poller_state.json`) in the same Docker volume. The poller writes device-in-progress state, suppression flags, and pending upgrade data. The server reads and writes suppression flags when a device is deleted. The poller reloads this file at the top of every 30-second poll cycle.

This pattern avoids a message broker or shared memory and works across two separate processes (and two separate containers) with no additional dependencies. File permissions (664, `ztpadmin:root`) allow both the server process and the root-running poller to write.

### Docker and Docker Compose — Process Isolation

The ZTP stack runs as two Docker containers defined in `docker-compose.yml`:

- **registry** — Flask app, bound to host port 5000, mounts the `ztp-data` volume and the `ansible/` directory
- **poller** — background daemon, shares the same `ztp-data` volume, requires host network access to reach the OpenGear REST API and the registry API

The same `docker-compose.yml` deploys to both the Linux development server and the OpenGear (the active production host). A `deploy.sh` script handles `rsync` of source files and `docker-compose up --build` on the target.

### OpenGear CM8100 — Console Server

The OpenGear is a physical console server appliance that aggregates serial console connections from multiple switches into a single device accessible over the network. It exposes:

- **REST API v2** — used by the poller to enable port logging and retrieve buffered console output (`portlog`) for each connected switch
- **WebSocket console** — used for optional switch-console access through the OpenGear web UI

The poller connects to `https://192.0.2.253/api/v2` with HTTP basic auth, disabling TLS certificate validation (self-signed cert). It enables `logging_level: eventsAndAllCharacters` on each console port and fetches the last 1000 lines of portlog on every poll cycle.

### Cisco PnP (Plug and Play) Protocol — Switch Auto-Discovery

When a Cisco Catalyst switch boots with no startup configuration, it enters PnP mode and broadcasts a DHCP request. The DHCP server (dnsmasq) responds with an IP address and DHCP option 150, which points the switch to a TFTP/HTTP boot URL on the ZTP server. The switch's PnP agent downloads and executes the script at that URL — this is `ztp.py`.

This is all Cisco-standard behavior. The ZTP server does not need any special Cisco integration beyond serving a valid Python script at the expected URL.

### dnsmasq — DHCP Server

dnsmasq runs on the OpenGear and handles DHCP for the `192.0.2.0/24` ZTP subnet. It assigns IP addresses to switches as they boot and injects DHCP option 150 pointing to `http://192.0.2.253:8080/ztp.py` (the boot script URL served by nginx).

### nginx — Static File Server

A separate nginx instance (not Flask) serves the files that switches download during provisioning:

- `ztp.py` — the provisioning script
- `config.json` — target IOS version, switch credentials (hashed), management interface config
- IOS-XE `.bin` image files — downloaded by the switch if an upgrade is needed

nginx serves these on port 80 (on the OpenGear) and port 8080 (on the Linux server). These are large binary files; nginx handles them efficiently without involving Python.

A second nginx instance on the Linux server (192.0.2.14) acts as a reverse proxy, exposing the ZTP dashboard and OpenGear management UI to the user network (198.51.100.0/24) — see the Reverse Proxy section below.

### ztp.py — On-Switch Provisioning Script

This is the most constrained component. It runs inside Cisco's **Guest Shell** — a Linux container embedded in IOS-XE — using a Python interpreter provided by Cisco with no third-party packages available. Only Python standard library modules can be used (`urllib.request`, `json`, `subprocess`, etc.).

What it does, in order:

1. Calls `GET /api/lookup/<serial>` on the registry to retrieve the assigned hostname
2. Downloads `config.json` from the nginx server
3. Runs IOS CLI commands via `subprocess` to apply hostname, credentials, SSH, and management interface config
4. Runs `show version` to detect the current IOS-XE version
5. If version doesn't match the target: downloads the IOS image, runs `install add activate commit`, and reloads
6. Throughout execution, prints structured marker lines to the console (`ZTP-SERIAL:`, `ZTP-MODEL:`, `ZTP-VERSION:`, `ZTP-PROGRESS:`, `ZTP-INV-ITEM-N:`) that the poller later parses from the portlog

The script is served over HTTP and executes immediately on the next booting switch — there is no staging or versioning mechanism. Changes are live for all subsequent switches.

### opengear_poller.py — Log Parser and Device Registrar

The poller runs in a 30-second loop and does the following each cycle:

1. Loads `.poller_state.json` to pick up suppression flags and pending state
2. For each monitored console port (ports 2–8), fetches the last 1000 lines of portlog via the OpenGear REST API
3. Parses the portlog for ZTP marker lines emitted by `ztp.py`
4. Detects session boundaries — distinguishes a fresh ZTP run from stale buffered output of a previous session using boot sequence markers (`RESTART`, `Initializing Hardware`, `Press RETURN`)
5. Posts live session status updates to `POST /api/live-session` (picked up by Flask and fanned out via SSE to browsers)
6. When ZTP completes: `POST /api/devices` to register the device in the database
7. For upgrade flows: saves device data to `pending` state in the JSON file, waits for the switch to reboot on new IOS, then registers after the reboot is confirmed

Upgrade parsing is intentionally conservative. OpenGear only returns the last 1000 portlog lines, and IOS install output can consume most of that buffer. When `Upgrade triggered` is present, reboot/bootstrap markers after the ZTP lines do not invalidate the session; the parser keeps returning `status='upgrading'` until the poller can persist the device data in `pending`. Non-upgrade sessions still treat those same reboot markers as stale output.

Suppression prevents re-registration: when a device is deleted from the dashboard, the server writes a `suppressed: true` flag with a UTC timestamp to the poller state. The poller ignores portlog entries timestamped before the suppression time, allowing the port to be reused without a false re-registration.

### Lookup System — Serial to Hostname Mapping

`lookup.py` maps a switch serial number to its hostname, building, and room. It reads from `device_lookup.csv`, which is generated by running `merge_lookup.py` against two source spreadsheets:

- **spreadsheet1.csv** — serial number → part number (PID)
- **spreadsheet2.csv** — part number → building, room, role, module

Hostnames are constructed at runtime using the formula: `{BUILDING}-{ROOM}-{MODEL_DIGITS}-{ROLE}`. Model digits are the first 4-digit sequence in the Cisco PID (e.g., `C9300X-48HX` → `9300`).

The CSV file is hot-reloaded on mtime change — no service restart needed when new devices are added.

### Vanilla JavaScript — Browser Dashboard

`static/index.html` is a single self-contained HTML file with embedded CSS and JavaScript. No build step, no npm, no framework. Dependencies:

- **EventSource API** — native browser SSE client, connects to `/api/stream` for real-time updates
- **Fetch API** — all API calls (GET devices, PUT updates, POST manual add, DELETE)
- **`window.print()`** — label printing opens a new browser window with label HTML (4"×6" formatted) and calls `print()` after a short delay

Device status (Pending vs. Complete) is computed client-side: a device is Complete when the required fields (building, room, asset_tag) are non-empty.

### Ansible — Post-Provisioning Configuration

An `ansible/` directory is mounted into the registry container. The Flask API exposes endpoints to list available playbooks, retrieve playbook YAML, and run a playbook against a specific device IP. Execution streams output back to the browser via SSE.

Playbooks use vault-encrypted credentials stored in `group_vars/all`. The vault password file is placed manually at `ansible/.vault_pass.txt` and never committed to git.

Key playbooks:
- **configure_device.yml** — applies full production configuration (VLANs, interfaces, routing)
- **version_checker.yml** — audits IOS-XE versions across all registered devices, produces a report

### nginx Reverse Proxy — User Network Access

Users on 198.51.100.0/24 cannot reach 192.0.2.253 directly (different subnet, no routing). The Linux server is dual-homed and runs nginx as a reverse proxy:

| Listen | Upstream | Purpose |
|--------|----------|---------|
| `https://198.51.100.14:8080` (TLS, self-signed) | `https://192.0.2.253:443` | OpenGear management UI |
| `http://198.51.100.14:5000` | `http://192.0.2.253:5000` | ZTP dashboard + API |

The OpenGear proxy requires HTTPS on the nginx listener side because the OpenGear console terminal uses `wss://` (secure WebSocket). If the proxy served plain HTTP, the browser would attempt `ws://` and the WebSocket handshake would fail. `proxy_buffering off` and the `Upgrade`/`Connection` headers are set to support WebSocket passthrough.

The ZTP dashboard proxy sets `proxy_buffering off` and a 3600-second read timeout to keep SSE connections open through the proxy without nginx closing them as idle.

---

## Data Flow: Normal Provisioning

```
Switch boots (no config)
  │
  ▼
DHCP request → dnsmasq assigns IP, returns option 150 boot URL
  │
  ▼
Switch PnP downloads ztp.py from nginx (port 80)
  │
  ▼
ztp.py runs on switch:
  ├── GET /api/lookup/<serial> → Flask returns hostname
  ├── GET config.json → nginx returns target version + credentials
  ├── Applies config via IOS CLI
  └── Emits ZTP-SERIAL, ZTP-MODEL, ZTP-VERSION, ZTP-INV-ITEM-N, ZTP-PROGRESS to console
  │
  ▼
OpenGear console port captures all output into portlog
  │
  ▼
Poller (30s cycle) fetches portlog via OpenGear REST API
  ├── Parses ZTP markers
  ├── POSTs live session status to Flask → SSE fans out to browsers
  └── On completion: POSTs device record to Flask → SQLite insert
  │
  ▼
Dashboard (browser) receives SSE update → device appears as Pending
  │
  ▼
User:
  ├── Reads MTAG from box/chassis label
  ├── Enters MTAG in dashboard → PUT /api/devices/<id>
  └── Clicks Print Label → browser print dialog → 4"×6" label
  │
  ▼
Status → Complete. Switch disconnected and repackaged.
```

## Data Flow: IOS Upgrade

```
ztp.py detects version mismatch
  │
  ▼
Downloads IOS image from nginx (may take 5–15 min)
  │
  ▼
Runs: install add file flash:/<image>.bin activate commit
  │
  ▼
Switch reloads automatically
  │
  ▼
Poller detects reload markers in portlog → saves device data to "pending" in state file
  │
  ▼
Switch reboots on new IOS → PnP runs again (brief) → ztp.py runs again
  │
  ▼
Poller detects post-reboot ZTP markers or boot-complete prompt → reads pending data → registers device in DB
  │
  ▼
Device appears in dashboard (with updated IOS version)
```

---

## Key Design Decisions

**Single-file server.** Everything in `server.py` — no blueprints, no service layer, no ORM. The codebase is small enough that the overhead of abstraction exceeds its benefit.

**File-based IPC over message broker.** A Redis or RabbitMQ instance would be operationally complex on an embedded device like the OpenGear. A JSON file on a shared Docker volume achieves the same result with zero additional dependencies.

**ztp.py stdlib-only.** Cisco's Guest Shell Python environment has no pip. Any third-party import would silently fail or crash. The script is intentionally constrained to what the target environment guarantees.

**Deferred registration on upgrade.** The switch reboots during an IOS upgrade and the portlog temporarily loses context. Rather than registering an incomplete record, the poller holds all device data in pending state until the post-reboot ZTP run or boot prompt confirms the reload completed. Parser stale-session logic must not discard `upgrading` sessions before that pending state is written.

**SSE over WebSockets for dashboard updates.** SSE is unidirectional (server → client), which is all that's needed for device table updates. It works through standard HTTP proxies without the `Upgrade` header negotiation that WebSockets require, simplifying the nginx proxy config for that endpoint.

**Hot-reload CSV lookup.** Restarting the Docker stack to add new device serials would interrupt in-flight provisioning sessions. The CSV loader checks file mtime on every lookup and reloads if changed, allowing live updates with no downtime.
