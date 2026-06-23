# Zero Touch Provisioning (ZTP) — Executive Overview

## What It Does

When a new network switch arrives and is plugged in, it configures itself automatically — no one needs to sit at a console and type commands. Within minutes of being connected to power and the network, the switch has the correct name, settings, and software version, and it appears in a web dashboard ready for the team to tag and document.

---

## The Problem It Solves

Traditionally, provisioning a new switch required someone to:

1. Physically connect a laptop to the switch via a serial cable
2. Manually type 20–30 configuration commands
3. Verify the software version and manually download an update if needed
4. Log the device in a spreadsheet

This process took 30–60 minutes per switch and was prone to typos, inconsistencies, and missed steps — especially during bulk deployments.

---

## How It Works (Plain English)

1. **Switch powers on** — The switch boots up and, finding no prior configuration, asks the network: *"Who am I and what should I do?"*

2. **Automatic identification** — Our system looks up the switch by its serial number (a unique ID printed on the hardware) and retrieves its assigned name, building, and room from a pre-loaded spreadsheet.

3. **Self-configuration** — The switch downloads and applies its configuration automatically: hostname, management settings, security policies, and NTP/syslog servers.

4. **Software check** — The switch compares its current software version against the approved standard. If it's out of date, it downloads and installs the correct version automatically.

5. **Dashboard registration** — Once provisioning is complete, the switch appears in the ZTP web dashboard with its hostname, location, IP address, and hardware details pre-populated. The remaining manual step is to add the asset tag and any notes.

---

## What Users See

A live web dashboard at `http://192.0.2.253:5000` that shows:

- All provisioned switches with hostname, location, IP, and hardware info
- Live status cards for switches currently provisioning
- Any switches that failed provisioning and why
- An Ansible automation panel for post-deployment tasks (e.g. running a software version audit across all switches)

---

## Business Value

| Before | After |
|--------|-------|
| 30–60 min per switch, manual | 5–10 min per switch, unattended |
| Configuration errors from manual entry | Consistent, policy-compliant config every time |
| Ad hoc spreadsheet tracking | Centralized dashboard with full audit trail |
| Manual console work required | Only final tagging remains manual |

For a deployment of 20 switches, this saves approximately **8–16 hours of manual labor** and eliminates an entire category of configuration drift errors.

---

## Key Components

| Component | Role |
|-----------|------|
| OpenGear CM8100 | Console server — physically connected to all switches; hosts the ZTP service |
| ZTP Registry (web dashboard) | Tracks all devices; provides lookup API for switches during provisioning |
| Ansible automation | Pushes configuration changes and runs compliance checks (e.g. software version audits) post-deployment |
| Device lookup data | Spreadsheet-sourced table mapping serial numbers to assigned hostnames and locations |

---

*Last updated: June 2026*
