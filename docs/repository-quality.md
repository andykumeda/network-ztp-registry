# Repository Quality And Security

The automated repository check catches common publication mistakes, including
credentials, machine-specific artifacts, non-example endpoints, private IPv4
addresses, absolute user paths, production-format serial numbers, and unexpected
Git author email addresses. With `--history`, it also checks every blob reachable
from local Git refs.

```bash
python3 scripts/check_repository.py --history
```

Projects that need additional restricted patterns can place them in the ignored
local file `.repository-denylist`, one per line, or pass them through the
`REPOSITORY_DENYLIST` environment variable. A GitHub Actions secret with that
name can extend the same check without committing the patterns.

Example addresses use the RFC 5737 documentation ranges. Replace them only in
an ignored `.env` file when running against a private lab.

The local demo binds to loopback. Browser-rendered registry values are escaped,
CSV exports neutralize spreadsheet formulas, and Ansible execution is disabled
unless an operator explicitly enables it for a controlled lab environment.
