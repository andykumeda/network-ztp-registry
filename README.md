# Network ZTP Registry

Network ZTP Registry is a reference Zero Touch Provisioning system for
network switch staging. It demonstrates how a small Flask service, a browser
dashboard, a console-server poller, and an on-device ZTP script can work
together to discover devices, track staging progress, capture hardware
inventory, and sync clean registry records to an optional ITSM/CMDB webhook.

The included demo uses fictional inventory and RFC 5737 example addresses so it
can run without access to external infrastructure.

## What It Shows

- Flask API with SQLite-backed device registry and Server-Sent Events updates
- Browser dashboard for live staging status, asset tagging, CSV export, labels,
  and ad hoc Ansible playbook execution
- Console-server poller that parses ZTP markers from serial logs
- On-switch Python ZTP script for first-boot configuration and inventory capture
- Optional outbound ITSM/CMDB webhook with batched best-effort delivery
- Local seeded demo that works without switches, OpenGear hardware, IOS images,
  or ITSM credentials

## Local Demo

### Python-only demo

Use Python 3.10 or newer (the macOS system Python may be older).

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-demo.txt
./launch-demo.command
```

Open <http://127.0.0.1:5055/>. On macOS, double-click `launch-demo.command`.
Other platforms can run `.venv/bin/python scripts/run_demo.py`. The runner seeds
only missing synthetic records, preserves edits, and forces Ansible execution
and ITSM delivery off. It uses ignored `.demo/` state. A busy port exits before
changing data.

Click **Simulate Boot** for a fictional browser-only console replay. It neither
executes switch commands nor registers devices. **Complete** means building,
room and asset tag are filled, not proven provisioning or network health.
See [the demo guide](docs/demo.md) for controls and handoff steps.

### Docker demo

```bash
docker compose -f docker-compose.demo.yml up --build
python scripts/seed_demo.py
```

Open <http://localhost:5000>.

## Hardware Lab Mode

Copy `.env.example` to `.env`, set lab-specific values, provide IOS images and
Ansible credentials, then use `docker-compose.yml`. The lab mode expects real
network access to a console server and a dedicated switch staging network.
The registry binds to loopback and Ansible execution stays disabled by default.
Expose either capability only on an isolated management network behind access
controls appropriate for an automation service.

## Repository Map

- `server.py` - Flask API, dashboard host, registry database, SSE, Ansible run API
- `static/index.html` - self-contained dashboard UI
- `opengear_poller.py` - console-server polling and ZTP marker parsing
- `ztp.py` - on-device Cisco PnP/ZTP script
- `lookup.py` - hot-reloaded CSV serial-to-PID lookup
- `itsm_push.py` - optional vendor-neutral ITSM/CMDB webhook worker
- `model-sn.csv`, `model-loc.csv` - fictional demo lookup data
- `docs/` - architecture, demo, and integration notes

## Validation

Run the repository quality checks and unit tests before publishing changes:

```bash
python3 scripts/check_repository.py --history
python3 -m unittest discover -s tests -v
```
