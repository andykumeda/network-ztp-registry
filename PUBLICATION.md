# Public Export Notes

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
