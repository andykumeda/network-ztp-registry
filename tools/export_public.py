#!/usr/bin/env python3
"""Export a sanitized source tree for the public GitHub repository.

The private repository contains site-specific runbooks, real serial/location
CSVs, runtime deployment paths, and vendored Ansible collections. This script
copies only the public-safe source files, rewrites known internal values to
documentation placeholders, and writes fake lookup CSVs for local demos.
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

COPY_FILES = [
    ".dockerignore",
    ".env.example",
    ".env.linux.example",
    ".env.opengear.example",
    ".gitignore",
    "config.json.example",
    "docker-compose.yml",
    "health-check.sh",
    "lookup.py",
    "opengear_poller.py",
    "requirements.txt",
    "server.py",
    "servicenow_push.py",
    "servicenow_query.py",
    "state_io.py",
    "tools/export_public.py",
    "ztp.py",
    "static/index.html",
    "docker/dhcp/Dockerfile",
    "docker/dhcp/dnsmasq.conf.tpl",
    "docker/dhcp/entrypoint.sh",
    "docker/nginx/nginx.conf",
    "docker/poller/Dockerfile",
    "docker/registry/Dockerfile",
    "docker/web/Dockerfile",
    "docker/web/entrypoint.sh",
    "docs/Technical_Overview.md",
    "docs/Technical_Summary.md",
    "docs/ZTP_Staging_SOP.md",
    "docs/overview.md",
    "docs/servicenow-integration.md",
    "docs/servicenow_sample.json",
    "ansible/.gitignore",
    "ansible/LICENSE",
    "ansible/README.md",
    "ansible/ansible.cfg",
    "ansible/inventory.example",
    "ansible/playbooks/backup_configs.yml",
    "ansible/playbooks/configure_device.yml",
    "ansible/playbooks/group_vars/all.example",
    "ansible/playbooks/version_checker.yml",
]

GENERATED_FILES = {
    "README.md",
    "PUBLICATION.md",
    "model-sn.csv",
    "model-loc.csv",
}

TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".css",
    ".csv",
    ".example",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".tpl",
    ".txt",
    ".yml",
    ".yaml",
}

LITERAL_REPLACEMENTS = {
    "192.0.2.253": "192.0.2.253",
    "192.0.2.14": "192.0.2.14",
    "192.0.2.100": "192.0.2.100",
    "192.0.2.200": "192.0.2.200",
    "192.0.2.1": "192.0.2.1",
    "192.0.2.0/24": "192.0.2.0/24",
    "198.51.100.14": "198.51.100.14",
    "198.51.100.0/24": "198.51.100.0/24",
    "198.51.100.10": "198.51.100.10",
    "example.service-now.com": "example.service-now.com",
    "example.org": "example.org",
    "maintainer@example.com": "maintainer@example.com",
    "example-org": "example-org",
    "ztpadmin": "ztpadmin",
    "Network ZTP Registry": "Network ZTP Registry",
    "Network": "Network",
}

REGEX_REPLACEMENTS = [
    # Sanitise Cisco-like serials in copied docs without touching placeholder text.
    (re.compile(r"\b(?:FOX|FVH|FJC|FJL|FLM|DCC|DTM|FDO|FJZ)[0-9A-Z]{7,}\b"), "SERIAL000001"),
    # Avoid leaking any remaining addresses from the production ZTP subnet.
    (re.compile(r"\b192\.168\.128\.(\d{1,3})\b"), r"192.0.2.\1"),
    # Avoid leaking the user-network proxy subnet.
    (re.compile(r"\b10\.151\.(\d{1,3})\.(\d{1,3})\b"), r"198.51.\1.\2"),
]

README = """# Network ZTP Registry

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
"""

PUBLICATION = """# Public Export Notes

This repository is generated from a private production repository by
`tools/export_public.py`.

Excluded from this public mirror:

- real serial/location lookup CSVs
- SQLite databases, poller state, `.env`, `config.json`, IOS images, and vault files
- private handoff notes and internal planning history
- docx exports and presentation drafts
- vendored Ansible collections
- production-specific Ansible playbooks with embedded ACLs or community names

Sanitization rules replace known internal IP addresses, domains, emails, account
names, and Cisco serial patterns with documentation placeholders. Review the diff
and run a leakage scan before every public push.
"""

MODEL_SN = """PID,SN
C9300X-48HX,SERIAL000001
C9300X-48HX,SERIAL000002
C9410R-96U-BNDL-A,SERIAL000003
"""

MODEL_LOC = """PID,Bldg,Floor,Rm,Role,Module
C9300X-48HX,LAB,1,101,EN,
C9300X-48HX,LAB,1,102,EN,C9300X-NM-2C
C9410R-96U-BNDL-A,DC,2,201,FB,(2) C9400-LC-48HN
"""


def is_text(path: Path) -> bool:
    return path.name in {".gitignore", ".dockerignore"} or path.suffix in TEXT_SUFFIXES


def sanitize(text: str) -> str:
    for old, new in LITERAL_REPLACEMENTS.items():
        text = text.replace(old, new)
    for pattern, replacement in REGEX_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text.rstrip() + "\n" if text else text


def clean_target(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in target.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def copy_file(relative: str, target: Path) -> None:
    src = ROOT / relative
    if not src.exists():
        raise FileNotFoundError(relative)

    dst = target / relative
    dst.parent.mkdir(parents=True, exist_ok=True)

    if is_text(src):
        dst.write_text(sanitize(src.read_text(encoding="utf-8")), encoding="utf-8")
    else:
        shutil.copy2(src, dst)


def write_generated(target: Path) -> None:
    files = {
        "README.md": README,
        "PUBLICATION.md": PUBLICATION,
        "model-sn.csv": MODEL_SN,
        "model-loc.csv": MODEL_LOC,
    }
    for relative, text in files.items():
        dst = target / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")


def chmod_scripts(target: Path) -> None:
    for relative in ("health-check.sh", "docker/dhcp/entrypoint.sh", "docker/web/entrypoint.sh"):
        path = target / relative
        if path.exists():
            path.chmod(path.stat().st_mode | 0o111)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        type=Path,
        help="Path to the checked-out public repository. Its .git directory is preserved.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target = args.target.resolve()

    clean_target(target)
    for relative in COPY_FILES:
        copy_file(relative, target)
    write_generated(target)
    chmod_scripts(target)

    copied = len(COPY_FILES) + len(GENERATED_FILES)
    print(f"Exported {copied} public-safe files to {target}")


if __name__ == "__main__":
    main()
