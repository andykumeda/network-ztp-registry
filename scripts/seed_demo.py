#!/usr/bin/env python3
"""Seed synthetic records into a local Network ZTP Registry demo."""

import json
import sys
import urllib.error
import urllib.request


BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:5000"


DEVICES = [
    {
        "hostname": "HQ-101-9300-ACCESS",
        "model": "C9300X-48HX-A",
        "serial": "DEMO9300X001",
        "ip_address": "10.10.10.101",
        "building": "HQ",
        "floor": "1",
        "room": "101",
        "module": "C9300X-NM-2C",
        "asset_tag": "ASSET-0001",
        "notes": "Seeded access switch demo record",
        "ios_version": "17.12.1",
        "port_label": "Demo Port 1",
        "hw_inventory": [
            {"name": "Chassis", "pid": "C9300X-48HX-A", "sn": "DEMO9300X001"},
            {"name": "Network Module", "pid": "C9300X-NM-2C", "sn": "DEMONM001"},
            {"name": "Power Supply A", "pid": "PWR-C1-1100WAC-P", "sn": "DEMOPSU001"},
        ],
    },
    {
        "hostname": "HQ-MDF-9410-DIST",
        "model": "C9410R-96U-BNDL-A",
        "serial": "DEMO9410R001",
        "ip_address": "10.10.10.102",
        "building": "HQ",
        "floor": "1",
        "room": "MDF",
        "module": "(4) C9400-LC-48HN",
        "asset_tag": "ASSET-0002",
        "notes": "Seeded modular chassis demo record",
        "ios_version": "17.12.1",
        "port_label": "Demo Port 2",
        "hw_inventory": [
            {"name": "Chassis", "pid": "C9410R", "sn": "DEMO9410R001"},
            {"name": "Slot 1 Linecard", "slot": "1", "pid": "C9400-LC-48HN", "sn": "DEMOLC001"},
            {"name": "Slot 2 Linecard", "slot": "2", "pid": "C9400-LC-48HN", "sn": "DEMOLC002"},
            {"name": "Supervisor", "slot": "5", "pid": "C9400X-SUP-2", "sn": "DEMOSUP001"},
            {"name": "Power Supply Module 1", "pid": "C9400-PWR-3200AC", "sn": "DEMOPSU002"},
        ],
    },
    {
        "hostname": "LAB-201-9300-ACCESS",
        "model": "C9300X-24HX-A",
        "serial": "DEMO9300X003",
        "ip_address": "10.10.10.103",
        "building": "LAB",
        "floor": "2",
        "room": "201",
        "module": "",
        "asset_tag": "",
        "notes": "Pending asset tag demo record",
        "ios_version": "17.12.1",
        "port_label": "Demo Port 3",
        "hw_inventory": [
            {"name": "Chassis", "pid": "C9300X-24HX-A", "sn": "DEMO9300X003"}
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
