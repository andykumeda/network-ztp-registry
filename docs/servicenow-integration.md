# ServiceNow Integration Guide — ZTP Device Registry

This document describes how to import device records from the ZTP registry into ServiceNow and optionally keep them in sync on a recurring schedule.

---

## Data Source

The ZTP registry exposes a REST API that returns all provisioned devices as JSON:

```
GET http://192.0.2.253:5000/api/devices
```

No authentication is required. The endpoint returns an array of device objects. A CSV download is also available for one-time manual imports:

```
GET http://192.0.2.253:5000/api/devices/export.csv
```

### Field Reference

| ZTP Field | Description | Example |
|-----------|-------------|---------|
| `hostname` | Assigned device name | `HRW-1318-9410-EN` |
| `serial` | Chassis serial number | `SERIAL000001` |
| `model` | Cisco part number | `C9410R` |
| `ip_address` | Management IP address | `192.0.2.141` |
| `building` | Building code | `HRW` |
| `floor` | Floor (may be null) | `3` |
| `room` | Room number | `1318` |
| `module` | Linecard/module summary | `(5) C9400-LC-48HN` |
| `ios_version` | IOS XE version at provisioning | `17.18.2` |
| `asset_tag` | MTAG / asset tag (may be null) | `IT-00423` |
| `notes` | Free-text notes | |
| `status` | Provisioning status | `complete` |
| `provisioned_at` | ISO 8601 timestamp of first provisioning | `2026-04-20T22:23:52Z` |
| `updated_at` | ISO 8601 timestamp of last update | `2026-04-20T22:23:52Z` |

---

## Option A — One-Time CSV Import

Use this for an initial bulk load.

1. Download the CSV: `http://192.0.2.253:5000/api/devices/export.csv`
2. In ServiceNow, navigate to **System Import Sets > Load Data**
3. Select **File** as the source, upload the CSV
4. Create a new import set table (e.g. `u_ztp_import`)
5. Run the import and proceed to **Option A/B Transform Map** below

---

## Option B — Scheduled REST Import (Recommended)

This keeps ServiceNow in sync automatically without manual exports.

### Step 1 — Create a REST Message

1. Navigate to **System Web Services > Outbound > REST Message**
2. Click **New** and fill in:
   - **Name:** `ZTP Device Registry`
   - **Endpoint:** `http://192.0.2.253:5000/api/devices`
   - **Authentication:** None
3. Under **HTTP Methods**, create a method:
   - **Name:** `get_devices`
   - **HTTP Method:** GET
4. Save

### Step 2 — Create an Import Set Table

1. Navigate to **System Import Sets > Create Import Set Table**
2. **Label:** `ZTP Devices Import`
3. **Name:** `u_ztp_devices_import` (auto-suggested)
4. Add the following fields (all String unless noted):

| Field Label | Field Name | Type |
|-------------|------------|------|
| Hostname | u_hostname | String (100) |
| Serial | u_serial | String (50) |
| Model | u_model | String (50) |
| IP Address | u_ip_address | String (50) |
| Building | u_building | String (20) |
| Floor | u_floor | String (10) |
| Room | u_room | String (20) |
| Module Summary | u_module | String (200) |
| IOS Version | u_ios_version | String (30) |
| Asset Tag | u_asset_tag | String (50) |
| Notes | u_notes | String (500) |
| Status | u_status | String (30) |
| Provisioned At | u_provisioned_at | String (50) |

### Step 3 — Create a Scheduled Import

1. Navigate to **System Import Sets > Scheduled Imports**
2. Click **New** and fill in:
   - **Name:** `ZTP Device Registry Sync`
   - **Import set table:** `u_ztp_devices_import`
   - **Data source:** Create new with type **REST**, pointing to the REST Message created in Step 1
   - **Run:** Daily (or at your preferred interval)
3. Save

### Step 4 — Create a Transform Map

1. Navigate to **System Import Sets > Transform Maps**
2. Click **New**:
   - **Name:** `ZTP to CMDB`
   - **Source table:** `u_ztp_devices_import`
   - **Target table:** `cmdb_ci_network_gear` (or your preferred CI class)
3. Add field mappings:

| Source Field | Target Field | Notes |
|--------------|--------------|-------|
| `u_hostname` | `name` | |
| `u_serial` | `serial_number` | |
| `u_model` | `model_id` | May need a reference lookup |
| `u_ip_address` | `ip_address` | |
| `u_asset_tag` | `asset_tag` | |
| `u_ios_version` | `os_version` | |
| `u_provisioned_at` | `install_date` | |

4. Set **Coalesce** on `u_serial` → `serial_number` so re-imports update existing records rather than creating duplicates

---

## Notes for the ServiceNow Admin

- **Source network:** The ZTP registry runs on the internal network at `192.0.2.253`. Ensure the ServiceNow MID Server (if used) has network access to that IP on port 5000.
- **Null fields:** `floor`, `asset_tag`, and `notes` may be null for newly provisioned devices. Map them permissively.
- **hw_inventory:** The raw API (`/api/devices`) includes a `hw_inventory` JSON field with individual component serials (linecards, supervisors, PSUs). If individual component CIs are needed, contact the network team — this data is available but requires additional transform logic.
- **Record of truth:** During active deployments, the ZTP registry is updated in real time. For a stable CMDB, schedule the sync to run nightly off-hours.

---

*Last updated: June 2026*
*Contact: maintainer@example.com*
