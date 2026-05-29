# Demo Guide

The demo path uses only synthetic sample data.

## Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-demo.txt
python server.py
```

Seed sample records:

```bash
source .venv/bin/activate
python scripts/seed_demo.py
```

Open <http://localhost:5000>.

## Docker

```bash
docker compose -f docker-compose.demo.yml up --build
python scripts/seed_demo.py
```

The demo compose file runs only the registry/dashboard service. It does not run
DHCP or the console poller, because those require real lab networking and
hardware.

## Reset Demo Data

For the Python demo, delete `devices.db`. For the Docker demo, remove the named
volume:

```bash
docker compose -f docker-compose.demo.yml down -v
```
