"""ServiceNow push integration for ZTP device registry.

Posts device records to ServiceNow's scripted REST endpoint
(u_mgn_staging import table) as a batched JSON array.

Design notes:
  - stdlib only — ztp.py on the switch has no third-party deps; the server
    and poller likewise avoid adding runtime deps where possible.
  - Best-effort: push failures must never block or roll back local DB writes.
    Errors are logged; the local registry remains the source of truth.
  - Batched: callers invoke ``push_device_async`` which queues the payload.
    A single background worker drains the queue in short time windows
    (SERVICENOW_BATCH_WINDOW seconds) and POSTs each window as one array.
    Requested by the ServiceNow admin to minimize load on their side.
  - Deduped per batch: if the same serial appears multiple times in one
    window (e.g. rapid create+update), only the most recent payload is sent.
    ServiceNow-side coalesce on serial_number handles cross-batch dedupe.
"""

import base64
import json
import logging
import os
import queue
import threading
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_URL          = os.environ.get('SERVICENOW_URL', '').strip()
_USER         = os.environ.get('SERVICENOW_USER', '').strip()
_PASS         = os.environ.get('SERVICENOW_PASS', '')
_ENABLED      = os.environ.get('SERVICENOW_ENABLED', 'false').lower() == 'true'
_TIMEOUT      = int(os.environ.get('SERVICENOW_TIMEOUT', '10'))
_BATCH_WINDOW = float(os.environ.get('SERVICENOW_BATCH_WINDOW', '10'))

_queue: 'queue.Queue[dict]' = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()


def _to_payload(device: dict) -> dict:
    """Map a ZTP device row (dict from sqlite3.Row) to the flat ServiceNow payload.

    Field names are lowercase snake_case. The ServiceNow admin has mapped these
    directly as u_mgn_staging column labels (no u_ prefix needed).
    """
    hw = device.get('hw_inventory')
    if isinstance(hw, (list, dict)):
        hw = json.dumps(hw)
    return {
        'hostname':       device.get('hostname'),
        'serial_number':  device.get('serial'),
        'model':          device.get('model'),
        'ip_address':     device.get('ip_address'),
        'building':       device.get('building'),
        'floor':          device.get('floor'),
        'room':           device.get('room'),
        'module':         device.get('module'),
        'asset_tag':      device.get('asset_tag'),
        'notes':          device.get('notes'),
        'ios_version':    device.get('ios_version'),
        'port_label':     device.get('port_label'),
        'hw_inventory':   hw,
        'status':         device.get('status') or 'provisioned',
        'failure_reason': device.get('failure_reason'),
        'provisioned_at': device.get('provisioned_at'),
        'updated_at':     device.get('updated_at'),
    }


def _post_batch(batch: list) -> None:
    """POST a batched JSON array to ServiceNow. Logs on error, never raises."""
    if not (_URL and _USER and _PASS):
        logger.warning('servicenow_push: missing URL/USER/PASS — skipping batch of %d', len(batch))
        return
    if not batch:
        return

    body = json.dumps(batch).encode('utf-8')
    auth = base64.b64encode(f'{_USER}:{_PASS}'.encode()).decode()
    req = urllib.request.Request(
        _URL,
        data=body,
        method='POST',
        headers={
            'Content-Type':  'application/json',
            'Accept':        'application/json',
            'Authorization': f'Basic {auth}',
        },
    )
    serials = [p.get('serial_number') for p in batch]
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            status = resp.status
            if 200 <= status < 300:
                logger.info('servicenow_push: ok count=%d status=%s serials=%s',
                            len(batch), status, serials)
            else:
                logger.warning('servicenow_push: non-2xx count=%d status=%s body=%s',
                               len(batch), status, resp.read()[:500])
    except urllib.error.HTTPError as e:
        logger.warning('servicenow_push: HTTP %s count=%d serials=%s body=%s',
                       e.code, len(batch), serials, e.read()[:500])
    except urllib.error.URLError as e:
        logger.warning('servicenow_push: URL error count=%d serials=%s reason=%s',
                       len(batch), serials, e.reason)
    except Exception as e:
        logger.warning('servicenow_push: unexpected error count=%d serials=%s err=%s',
                       len(batch), serials, e)


def _dedupe(batch: list) -> list:
    """Within a batch, keep only the most recent payload per serial_number.
    Preserves original order of first occurrence so ordering is stable."""
    order: list = []
    latest: dict = {}
    for p in batch:
        sn = p.get('serial_number')
        if sn is None:
            order.append(len(order))
            latest[len(order) - 1] = p
            continue
        if sn not in latest:
            order.append(sn)
        latest[sn] = p
    return [latest[k] for k in order]


def _worker() -> None:
    while True:
        # Block until at least one payload arrives
        first = _queue.get()
        batch = [first]
        deadline = time.monotonic() + _BATCH_WINDOW
        # Drain any additional payloads that arrive within the window
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                item = _queue.get(timeout=remaining)
                batch.append(item)
            except queue.Empty:
                break
        _post_batch(_dedupe(batch))


def _ensure_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        t = threading.Thread(target=_worker, name='servicenow-push', daemon=True)
        t.start()
        _worker_started = True


def push_device_async(device: dict) -> None:
    """Queue a device for push. Non-blocking. Safe to call on hot path."""
    if not _ENABLED:
        return
    _ensure_worker()
    _queue.put(_to_payload(device))
