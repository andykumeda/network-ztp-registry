# Network ZTP Registry

Network ZTP Registry is a portfolio-safe Zero Touch Provisioning system for
network switch staging. It demonstrates how a small Flask service, a browser
dashboard, a console-server poller, and an on-device ZTP script can work
together to discover devices, track staging progress, capture hardware
inventory, and sync clean registry records to an optional ITSM/CMDB webhook.

This public version uses synthetic data and generic lab addresses. It is not a
copy of a production deployment, and no real serial numbers, hostnames,
credentials, room mappings, or customer data are included.

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

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-demo.txt
python server.py
```

In a second terminal:

```bash
source .venv/bin/activate
python scripts/seed_demo.py
```

Open <http://localhost:5000>.

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

## Repository Map

- `server.py` - Flask API, dashboard host, registry database, SSE, Ansible run API
- `static/index.html` - self-contained dashboard UI
- `opengear_poller.py` - console-server polling and ZTP marker parsing
- `ztp.py` - on-device Cisco PnP/ZTP script
- `lookup.py` - hot-reloaded CSV serial-to-PID lookup
- `itsm_push.py` - optional vendor-neutral ITSM/CMDB webhook worker
- `model-sn.csv`, `model-loc.csv` - sanitized demo lookup data
- `docs/` - architecture, demo, and integration notes

## Sanitization Notice

All public data is synthetic. Private operational runbooks, generated handoff
documents, real lookup tables, vendored Ansible collections, and environment
specific deployment material were intentionally excluded from this portfolio
release.
