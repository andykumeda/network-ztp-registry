# Network ZTP Registry — Technical Summary

**Zero Touch Provisioning for Cisco Catalyst 9000 Series**

---

## Overview

An automated switch staging platform. Switches self-provision on first boot with no manual console interaction. A web dashboard tracks staging progress and serves as the asset registry.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API & Dashboard | Python / Flask |
| Database | SQLite |
| Real-time updates | Server-Sent Events (SSE) |
| Containerization | Docker / Docker Compose |
| Console aggregation | OpenGear CM8100 (REST API) |
| Switch auto-discovery | Cisco Plug and Play (PnP) |
| DHCP | dnsmasq |
| Static file serving | nginx |
| On-switch scripting | Python (stdlib only — runs in Cisco Guest Shell) |
| Post-provisioning config | Ansible |
| Reverse proxy | nginx |
| Frontend | Vanilla JavaScript / HTML (no framework) |

---

## How It Ties Together

**Provisioning flow:**

1. Switch boots with no config → broadcasts DHCP request
2. DHCP server responds with an IP and a boot script URL
3. Switch downloads and executes a Python provisioning script via Cisco PnP
4. Script queries the registry API for the assigned hostname, downloads device config, applies it, and upgrades IOS if needed — all autonomously
5. Script emits structured status markers to the serial console throughout execution
6. Console server captures all output and buffers it per port
7. Background polling daemon reads the console buffer every 30 seconds, parses the status markers, and registers the device in the database when provisioning completes
8. Browser dashboard receives a real-time push update and displays the new device
9. User enters the asset tag, saves, and prints a label
10. (Optional) User triggers an Ansible playbook from the dashboard — output streams back to the browser in real time

**IOS upgrade flow** (when version doesn't match target):

- Switch downloads the IOS image and reboots automatically
- Poller holds the device record in pending state through the reboot
- After reboot, the provisioning script runs again briefly to confirm the new version
- Poller registers the final record once the upgraded version is verified

---

## Key Characteristics

- **No manual console access required** — users interact only with the browser
- **Up to 7 devices staged simultaneously**
- **Hot-reload device lookup** — new serials added without restarting services
- **Same stack deployed to two hosts** — development server and production console server run identical containers
- **All inter-process state** shared via a JSON file on a shared volume — no message broker needed
