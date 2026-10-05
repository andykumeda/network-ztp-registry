#!/usr/bin/env python3
"""Validate tracked content and reachable history for public distribution.

Add project-specific restricted patterns to the ignored local file
``.repository-denylist`` or pass them through ``REPOSITORY_DENYLIST``. The
denylist itself must never be committed.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTATION_NETWORKS = (
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
)
PRIVATE_NETWORKS = (
    ipaddress.ip_network((0x0A000000, 8)),
    ipaddress.ip_network((0xAC100000, 12)),
    ipaddress.ip_network((0xC0A80000, 16)),
)
IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
DOMAIN_RE = re.compile(
    r"\b(?:[A-Za-z0-9-]+\.)+"
    r"(?:com|org|net|edu|gov|io|tech|co|us|local|example|invalid)\b",
    re.IGNORECASE,
)
HOME_PATH_RE = re.compile(r"/(?:Users|home)/[^\s\"'<>]+")
CISCO_SERIAL_RE = re.compile(r"\b[A-Z]{3}\d{4}[A-Z0-9]{4}\b")
SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("credential in URL", re.compile(r"https?://[^\s/:]+:[^\s/@]+@")),
)
FORBIDDEN_SUFFIXES = (
    ".db",
    ".key",
    ".p12",
    ".pem",
    ".sqlite",
    ".sqlite3",
)
FORBIDDEN_NAMES = {".DS_Store", ".env", ".poller_state.json", ".vault_pass.txt"}
SAFE_DOMAIN_SUFFIXES = (".example", ".invalid", ".localhost", ".local")
SAFE_DOMAINS = {"example.com", "example.net", "example.org", "github.com"}


def git(*args: str) -> bytes:
    return subprocess.check_output(("git", "-C", str(ROOT), *args))


def parse_denylist(path: Path | None) -> list[str]:
    raw = os.environ.get("REPOSITORY_DENYLIST", "")
    if path and path.exists():
        raw += "\n" + path.read_text(encoding="utf-8")
    return [
        term.strip().casefold()
        for term in re.split(r"[,\n]", raw)
        if term.strip() and not term.lstrip().startswith("#")
    ]


def tracked_worktree_files() -> list[tuple[str, bytes]]:
    paths = [p for p in git("ls-files", "-z").split(b"\0") if p]
    return [
        (path.decode("utf-8", errors="replace"), (ROOT / os.fsdecode(path)).read_bytes())
        for path in paths
    ]


def historical_blobs() -> list[tuple[str, bytes]]:
    commits = [commit for commit in git("rev-list", "--all").splitlines() if commit]
    blobs: set[tuple[bytes, str]] = set()
    for commit in commits:
        entries = git("ls-tree", "-r", "-z", commit.decode())
        for entry in entries.split(b"\0"):
            if not entry:
                continue
            metadata, raw_path = entry.split(b"\t", 1)
            _mode, object_type, object_id = metadata.split()
            if object_type == b"blob":
                blobs.add((object_id, raw_path.decode("utf-8", errors="replace")))
    return [
        (f"history:{object_id.decode()[:12]}:{path}", git("cat-file", "blob", object_id.decode()))
        for object_id, path in sorted(blobs)
    ]


def filename_findings(source: str) -> list[str]:
    path = source.split(":", 2)[2] if source.startswith("history:") else source
    pure_path = PurePosixPath(path)
    name = pure_path.name
    findings = []
    if name in FORBIDDEN_NAMES or name.endswith(FORBIDDEN_SUFFIXES):
        findings.append(f"{source}: forbidden sensitive artifact name")
    if any(part in {".claude", ".venv", "__pycache__"} for part in pure_path.parts):
        findings.append(f"{source}: local/generated directory is tracked")
    return findings


def text_findings(source: str, data: bytes, denylist: list[str]) -> list[str]:
    if b"\0" in data:
        return []
    text = data.decode("utf-8", errors="replace")
    findings = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        folded = line.casefold()
        if any(term in folded for term in denylist):
            findings.append(f"{source}:{line_number}: denylisted organization identifier")
        if HOME_PATH_RE.search(line):
            findings.append(f"{source}:{line_number}: absolute user home path")
        if EMAIL_RE.search(line):
            findings.append(f"{source}:{line_number}: email address")
        for domain in DOMAIN_RE.findall(line):
            normalized = domain.casefold()
            if (
                any(normalized == domain or normalized.endswith(f".{domain}") for domain in SAFE_DOMAINS)
                or normalized.endswith(SAFE_DOMAIN_SUFFIXES)
            ):
                continue
            findings.append(f"{source}:{line_number}: non-example domain name")
        if CISCO_SERIAL_RE.search(line):
            findings.append(f"{source}:{line_number}: serial number matching a production format")
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(f"{source}:{line_number}: possible {label}")
        # Older synthetic examples can use RFC 1918 space without identifying
        # a real environment. Historical environment ranges are caught by the
        # private denylist; new tracked content must use documentation ranges.
        if source.startswith("history:"):
            continue
        for raw_ip in IPV4_RE.findall(line):
            try:
                address = ipaddress.ip_address(raw_ip)
            except ValueError:
                continue
            if any(address in network for network in DOCUMENTATION_NETWORKS):
                continue
            if any(address in network for network in PRIVATE_NETWORKS):
                findings.append(f"{source}:{line_number}: private IPv4 address")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--history",
        action="store_true",
        help="also scan every blob reachable from local Git refs",
    )
    parser.add_argument(
        "--denylist-file",
        type=Path,
        default=ROOT / ".repository-denylist",
        help="ignored local file containing additional restricted patterns",
    )
    args = parser.parse_args()

    denylist = parse_denylist(args.denylist_file)
    sources = tracked_worktree_files()
    if args.history:
        sources.extend(historical_blobs())

    findings = []
    for source, data in sources:
        findings.extend(filename_findings(source))
        findings.extend(text_findings(source, data, denylist))

    metadata = git("log", "--all", "--format=fuller").decode("utf-8", errors="replace")
    if any(term in metadata.casefold() for term in denylist):
        findings.append("git metadata: denylisted organization identifier")
    metadata_emails = EMAIL_RE.findall(metadata)
    # GitHub's generated PR merge commits use its platform no-reply identity.
    if any(
        not email.casefold().endswith('@users.noreply.github.com')
        and email.casefold() != 'noreply' + '@github.com'
        for email in metadata_emails
    ):
        findings.append("git metadata: non-noreply email address")

    unique_findings = list(dict.fromkeys(findings))
    if unique_findings:
        print("Repository check failed:", file=sys.stderr)
        for finding in unique_findings:
            print(f"- {finding}", file=sys.stderr)
        return 1

    scope = "tracked files and reachable history" if args.history else "tracked files"
    print(f"Repository check passed for {scope}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
