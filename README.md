# Network ZTP Registry

Public-safe source for a Cisco Catalyst Zero Touch Provisioning registry.

The stack combines:

- Flask + SQLite device registry and browser dashboard
- OpenGear console polling for ZTP progress and completion markers
- dnsmasq DHCP option delivery for Cisco PnP bootstrapping
- nginx static serving for `ztp.py`, `config.json`, and IOS images
- optional Ansible playbook execution after a switch is registered
- optional ServiceNow push integration

This repository is sanitized for public sharing. It includes fake lookup CSVs,
placeholder IP addresses from documentation ranges, and example configuration
only. It intentionally excludes private handoff notes, real serial/location
data, runtime databases, secrets, IOS images, generated docs, and vendored
Ansible collections.

## Local Shape

1. Copy `.env.example` to `.env` and adjust the placeholder network values.
2. Copy `config.json.example` to `config.json` and set target IOS metadata and
   switch credentials for your lab.
3. Put IOS `.bin` files in the directory referenced by `IOS_IMAGES_DIR`.
4. Run the stack with Docker Compose:

```bash
docker compose up -d --build
```

The dashboard listens on port `5000`. nginx serves ZTP assets on port `8080`
by default.

## Lookup Data

`model-sn.csv` maps serial number to Cisco PID. `model-loc.csv` maps planned
slots for each PID to building, floor, room, role, and expected module string.
The included files are fake examples only.

## Public Safety

Before pushing this mirror, regenerate it from the private repo:

```bash
python3 tools/export_public.py /path/to/network-ztp-registry
```

Then scan the public tree for internal IPs, domains, serials, and secret
patterns before committing.
