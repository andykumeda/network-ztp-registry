# ITSM Webhook Integration

`itsm_push.py` provides an optional outbound webhook for CMDB or ITSM systems.
It is disabled by default and never blocks registry writes.

## Environment

```bash
ITSM_ENABLED=false
ITSM_URL=https://itsm.example.com/api/network-ztp/devices
ITSM_USER=ztp-webhook-user
ITSM_PASS=change-me
ITSM_TIMEOUT=10
ITSM_BATCH_WINDOW=10
```

When enabled, registry create, update, delete, and post-playbook sync events are
queued in memory. A background worker batches events for `ITSM_BATCH_WINDOW`
seconds, deduplicates by `serial_number`, and posts a JSON array.

## Payload Shape

Each record is flat lowercase snake_case:

```json
{
  "hostname": "HQ-101-9300-ACCESS",
  "serial_number": "DEMO9300X001",
  "model": "C9300X-48HX-A",
  "ip_address": "10.10.10.101",
  "building": "HQ",
  "floor": "1",
  "room": "101",
  "module": "C9300X-NM-2C",
  "asset_tag": "ASSET-0001",
  "notes": "Seeded demo device",
  "ios_version": "17.12.1",
  "port_label": "Demo Port 1",
  "hw_inventory": "[]",
  "status": "provisioned",
  "failure_reason": null,
  "provisioned_at": "2026-01-01T00:00:00+00:00",
  "updated_at": "2026-01-01T00:00:00+00:00"
}
```
