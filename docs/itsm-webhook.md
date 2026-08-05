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
  "hostname": "DEMO-SWITCH-001",
  "serial_number": "DEMO-SERIAL-001",
  "model": "C9300-DEMO-48",
  "ip_address": "192.0.2.101",
  "building": "DEMO-A",
  "floor": "1",
  "room": "AREA-01",
  "module": "C9300-NM-DEMO",
  "asset_tag": "ASSET-0001",
  "notes": "Seeded demo device",
  "ios_version": "DEMO-IOS",
  "port_label": "Demo Port 1",
  "hw_inventory": "[]",
  "status": "provisioned",
  "failure_reason": null,
  "provisioned_at": "2026-01-01T00:00:00+00:00",
  "updated_at": "2026-01-01T00:00:00+00:00"
}
```
