#!/usr/bin/env python3
"""Seed synthetic records into a local Network ZTP Registry demo."""

import json
import sys
import urllib.error
import urllib.request


BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:5000"


DEVICES = [
    {
        "hostname": "DEMO-SWITCH-001",
        "model": "C9300-DEMO-48",
        "serial": "DEMO-SERIAL-001",
        "ip_address": "192.0.2.101",
        "building": "DEMO-A",
        "floor": "1",
        "room": "AREA-01",
        "module": "C9300-NM-DEMO",
        "asset_tag": "ASSET-0001",
        "notes": "Seeded access switch demo record",
        "ios_version": "DEMO-IOS",
        "port_label": "Demo Port 1",
        "hw_inventory": [
            {"name": "Chassis", "pid": "C9300-DEMO-48", "sn": "DEMO-SERIAL-001"},
            {"name": "Network Module", "pid": "C9300-NM-DEMO", "sn": "DEMO-MODULE-001"},
            {"name": "Power Supply A", "pid": "PWR-DEMO", "sn": "DEMO-POWER-001"},
        ],
    },
    {
        "hostname": "DEMO-SWITCH-002",
        "model": "C9400-DEMO-CHASSIS",
        "serial": "DEMO-SERIAL-002",
        "ip_address": "192.0.2.102",
        "building": "DEMO-A",
        "floor": "1",
        "room": "AREA-04",
        "module": "(2) C9400-LC-DEMO",
        "asset_tag": "ASSET-0002",
        "notes": "Seeded modular chassis demo record",
        "ios_version": "DEMO-IOS",
        "port_label": "Demo Port 2",
        "hw_inventory": [
            {"name": "Chassis", "pid": "C9400-DEMO-CHASSIS", "sn": "DEMO-SERIAL-002"},
            {"name": "Slot 1 Linecard", "slot": "1", "pid": "C9400-LC-DEMO", "sn": "DEMO-LINECARD-001"},
            {"name": "Slot 2 Linecard", "slot": "2", "pid": "C9400-LC-DEMO", "sn": "DEMO-LINECARD-002"},
            {"name": "Supervisor", "slot": "3", "pid": "C9400-SUP-DEMO", "sn": "DEMO-SUPERVISOR-001"},
            {"name": "Power Supply Module 1", "pid": "PWR-DEMO", "sn": "DEMO-POWER-002"},
        ],
    },
    {
        "hostname": "DEMO-SWITCH-003",
        "model": "C9300-DEMO-24",
        "serial": "DEMO-SERIAL-003",
        "ip_address": "192.0.2.103",
        "building": "DEMO-B",
        "floor": "2",
        "room": "AREA-03",
        "module": "",
        "asset_tag": "",
        "notes": "Pending asset tag demo record",
        "ios_version": "DEMO-IOS",
        "port_label": "Demo Port 3",
        "hw_inventory": [
            {"name": "Chassis", "pid": "C9300-DEMO-24", "sn": "DEMO-SERIAL-003"}
        ],
    },
]


def post_device(device: dict) -> None:
    body = json.dumps(device).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/devices",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"seeded {device['serial']} status={resp.status}")
    except urllib.error.HTTPError as exc:
        print(f"failed {device['serial']} HTTP {exc.code}: {exc.read().decode(errors='replace')}")
        raise


def main() -> None:
    for device in DEVICES:
        post_device(device)


if __name__ == "__main__":
    main()
