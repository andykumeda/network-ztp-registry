# Synthetic demo guide

Use Python 3.10 or newer. The macOS system Python may be older; select an
existing newer interpreter when creating the environment.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-demo.txt
./launch-demo.command
```

Open http://127.0.0.1:5055/. Double-clicking `launch-demo.command` on macOS does
the same thing. Leave its terminal open. Ctrl+C stops the server and preserves
data. On other platforms, use `.venv/bin/python scripts/run_demo.py`.

The runner forces Ansible execution and outbound ITSM off and binds only to
loopback. It starts no DHCP, console poller or hardware operation. It uses
fictional lookup CSVs and `.demo/devices.db`, separate from the normal database.
It creates only missing synthetic serials and never overwrites an edit.
A busy 5055 exits before creating or changing state; use the existing demo or
stop it in its own terminal first. No data deletion is needed.

## File map

| File | Purpose |
|---|---|
| `launch-demo.command` | macOS launcher with relative environment path |
| `scripts/run_demo.py` | Local safeguards, isolated state and missing-record seeding |
| `scripts/seed_demo.py` | Three fictional seed records |
| `server.py` | Flask API, SQLite registry and dashboard hosting |
| `static/index.html` | Dashboard and fictional boot replay |
| `model-sn.csv`, `model-loc.csv` | Fictional identity/location examples |
| `requirements-demo.txt` | Flask dependency; no hardware tools required |
| `.demo/` | Generated local state; ignored by Git |

No database, interpreter, credentials or customer data should be committed.

## What to show

Start with three records: two complete and one pending asset tag. Click
**Simulate Boot** for a 19-line accelerated fictional console sequence. It
illustrates boot, DHCP, script download, configuration and software checking.
Use Pause/Resume, Replay or Close. The replay never contacts hardware, executes
commands or changes inventory. Its fictional hostname is independent of the
registry's location-generated hostname.

Close the replay, open DEMO-SERIAL-003, inspect identity and add ASSET-0003.
Save to demonstrate a real local registry edit and dashboard update. Total
stays three; Pending becomes zero and Complete becomes three. To rehearse again,
clear only this synthetic asset tag and Save. Preserve the database and records.

**Complete** means building, room and asset tag are filled. A seed timestamp is
not a captured provisioning event. This demo does not prove IOS execution,
upgrades, console-poller behavior, network health or ServiceNow delivery.
The modular-chassis seed still registers if no lookup slot matches; do not use
these seeded records as proof of complete slot-matching correctness.

## Docker alternative

The existing `docker-compose.demo.yml` starts only the registry, without DHCP
or the poller, on loopback 5000. It is a separate route and does not use the
automatic seeding/state setup above. Use the Python runner on 5055 for this demo.

## Verification

```bash
.venv/bin/python scripts/check_repository.py --history
.venv/bin/python -m unittest discover -s tests -v
node tests/test_boot_replay.cjs
```

Replay checks cover syntax, completion, pause/resume, restart cancellation and
close. These checks verify synthetic application paths, not a live deployment.
