#!/usr/bin/env python3
"""OpenGear console port log poller.

Polls all console ports on the OpenGear appliance, enables port logging
if not already set, and parses ZTP output to register devices in server.py.

Environment variables:
  OPENGEAR_HOST      OpenGear IP/hostname (default: 10.10.10.20)
  OPENGEAR_USER      Username for OpenGear API authentication (required)
  OPENGEAR_PASSWORD  Password for OpenGear API authentication (required)
  OPENGEAR_SCHEME    http or https (default: https)
  OPENGEAR_PORT      Port number, blank = scheme default (default: blank)
  OPENGEAR_API       API base path (default: /api/v2, try /api/v1 if needed)
  SERVER_URL         Base URL of the Flask asset registry (default: http://localhost:5000)
  POLL_INTERVAL      Seconds between poll cycles (default: 60)
"""

import datetime
import http.cookiejar
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request

from state_io import load_state, save_state

# File to persist registered serials across poller restarts
_STATE_FILE = os.environ.get('POLLER_STATE_PATH',
                              os.path.join(os.path.dirname(os.path.abspath(__file__)), '.poller_state.json'))

OPENGEAR_HOST = os.environ.get('OPENGEAR_HOST', '10.10.10.20')
OPENGEAR_USER = os.environ.get('OPENGEAR_USER', '')
OPENGEAR_PASSWORD = os.environ.get('OPENGEAR_PASSWORD', '')
OPENGEAR_SCHEME = os.environ.get('OPENGEAR_SCHEME', 'https')
OPENGEAR_PORT = os.environ.get('OPENGEAR_PORT', '')
OPENGEAR_API = os.environ.get('OPENGEAR_API', '/api/v2')
SERVER_URL = os.environ.get('SERVER_URL', 'http://localhost:5000')
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', '30'))
DEBUG = os.environ.get('OPENGEAR_DEBUG', '').lower() in ('1', 'true', 'yes')

# OpenGear uses a self-signed TLS certificate
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

# Cookie jar preserves the session cookie across requests
_cookies = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_cookies),
    urllib.request.HTTPSHandler(context=_ssl_ctx),
)


def _base_url():
    host = f"{OPENGEAR_HOST}:{OPENGEAR_PORT}" if OPENGEAR_PORT else OPENGEAR_HOST
    return f"{OPENGEAR_SCHEME}://{host}{OPENGEAR_API}"


def _og_request(method, path, body=None, timeout=30):
    url = f"{_base_url()}{path}"
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_preview = e.read(200).decode(errors='replace')
        raise urllib.error.HTTPError(url, e.code, f"{e.reason} — URL: {url} — body: {body_preview}", e.headers, None)


def login():
    """POST credentials to /sessions; the server sets a session cookie on success."""
    result = _og_request('POST', '/sessions', body={
        'username': OPENGEAR_USER,
        'password': OPENGEAR_PASSWORD,
    })
    cookies_set = [c.name for c in _cookies]
    print(f"[opengear] Logged in. Session cookies: {cookies_set}. Response: {result}")


def get_ports():
    all_ports = _og_request('GET', '/ports').get('ports', [])
    # Ports wired to switches for ZTP. Expand as additional ports go into production.
    allowed_ids = ('ports-2', 'ports-3', 'ports-4', 'ports-5', 'ports-6', 'ports-7', 'ports-8')
    return [p for p in all_ports if p.get('id') in allowed_ids]


def enable_port_logging(port_id):
    current = _og_request('GET', f'/ports/{port_id}').get('port', {})
    current['logging_level'] = 'eventsAndAllCharacters'
    _og_request('PUT', f'/ports/{port_id}', body={'port': current})
    print(f"[opengear] Enabled logging on {port_id}")


def get_portlog(port_id):
    result = _og_request('GET', f'/logs/portlog/{port_id}?logLines=1000', timeout=60)
    return result.get('portlog', {}).get('log_lines', [])


def _last_console_line(lines):
    """Extract the last non-empty, meaningful RXDATA line from portlog.

    Filters out progress indicators (dots, hashes, exclamation marks),
    whitespace, control characters, and other download/boot noise so
    only real text messages are shown in the UI.
    """
    for line in reversed(lines):
        m = re.match(r"\S+\s+'[^']*'\s+RXDATA:\s*(.*)", line)
        if not m:
            continue
        text = m.group(1).strip()
        # Skip empty lines
        if not text:
            continue
        # Skip lines made entirely of progress/noise characters:
        #   #  hash bars (boot/install progress)
        #   .  dots (TFTP/copy transfer progress)
        #   !  exclamation marks (ping/copy progress)
        #   =  equal signs (loading bars)
        #   *  asterisks
        #   C  single repeated C's (rommon trying to boot)
        #   control chars (\x00-\x1f)
        if re.match(r'^[#.!=*C\-\s\x00-\x1f]+$', text):
            continue
        # Skip very short lines (1-2 chars) that are just noise
        if len(text) <= 2:
            continue
        # Skip lines that have no alphabetic content (just symbols/numbers)
        if not re.search(r'[a-zA-Z]{2,}', text):
            continue
        # Cap at 80 chars to prevent card overflow in UI
        return text[:80]
    return None


def parse_ztp_output(lines):
    """Parse portlog lines and extract ZTP device info and progress.

    Returns None if no ZTP activity. Otherwise returns a dict:
      progress        — latest ZTP-PROGRESS message (or last console line)
      console_line    — last meaningful console output line (always set)
      status          — 'provisioning' | 'upgrading' | 'staged' | 'failed'
      failure         — failure reason string (only present when status='failed')
      hostname        — set once 'Success: Hostname set to:' appears
      model/serial/ip_address/ios_version/hw_inventory — as available
    """
    rxdata = []
    for line in lines:
        m = re.match(r"\S+\s+'[^']*'\s+RXDATA:\s*(.*)", line)
        if m:
            rxdata.append(m.group(1))

    text = '\n'.join(rxdata)
    console_line = _last_console_line(lines)

    # Only parse the MOST RECENT ZTP session — old failures from previous
    # sessions would otherwise poison the current session's status
    boundaries = list(re.finditer(r'(?:ZTP-SERIAL:|Zero Touch Provisioning)', text))
    if boundaries:
        text = text[boundaries[-1].start():]

    # Require at least one ZTP marker
    if not re.search(r'ZTP-(?:SERIAL|MODEL|PROGRESS|FAILURE|VERSION|INVENTORY):', text):
        return None

    # Latest progress message
    progress_msgs = re.findall(r'ZTP-PROGRESS: (.+)', text)
    progress = progress_msgs[-1].strip() if progress_msgs else None

    # If there are ZTP markers (like ZTP-SERIAL:) but zero ZTP-PROGRESS
    # messages, the session data has scrolled out of the portlog buffer.
    # This is a stale session — not active ZTP.
    if not progress_msgs:
        return None

    # Determine status — check definitive completion FIRST so a prior
    # failure in the same portlog buffer doesn't override a success.
    failure = None
    if 'Script execution success' in text:
        status = 'staged'
    elif 'staging complete' in text.lower() or 'ios current' in text.lower():
        status = 'staged'
    elif re.search(r'ZTP-FAILURE: (.+)', text):
        status  = 'failed'
        failure = re.search(r'ZTP-FAILURE: (.+)', text).group(1).strip()
    elif 'Upgrade triggered' in text:
        status  = 'upgrading'
    else:
        status  = 'provisioning'

    # Detect stale session: if the device rebooted AFTER ZTP completed/failed,
    # the old markers are still in the portlog buffer but the device is starting
    # over.  Look for reboot indicators after the last ZTP completion marker.
    if status in ('staged', 'upgrading', 'failed'):
        # Find the position of the last ZTP marker
        last_ztp_pos = 0
        for m in re.finditer(r'(?:ZTP-PROGRESS:|ZTP-FAILURE:|Script complete)', text):
            last_ztp_pos = m.end()
        if last_ztp_pos:
            after_ztp = text[last_ztp_pos:]
            # These indicators mean the device has rebooted since ZTP finished.
            # NOTE: "Press RETURN" is NOT a reboot indicator — it appears
            # normally after ZTP script completion (PnP hands back control).
            if re.search(r'Initializing Hardware|System Bootstrap|RESTART|'
                         r'Rommon|switch:\s*$|Booting\.\.\.|IOSXEBOOT|'
                         r'boot:\s*attempting|SMART_LOG',
                         after_ztp, re.MULTILINE):
                # The ZTP session is over and the device has rebooted.
                # Return None so the caller treats this as "no active ZTP".
                # Pending upgrades are handled separately in poll().
                return None

    result = {'progress': progress, 'status': status}
    if console_line:
        result['console_line'] = console_line
    if failure:
        result['failure'] = failure

    hostname_m = re.search(r'Success: Hostname set to: (\S+)', text)
    if hostname_m:
        result['hostname'] = hostname_m.group(1)

    # Prefer explicit ZTP-MODEL line; fall back to deriving from hostname
    model_line_m = re.search(r'ZTP-MODEL: (\S+)', text)
    if model_line_m:
        result['model'] = model_line_m.group(1)
    elif hostname_m:
        model_num_m = re.match(r'(\d+)-ZTP-', result['hostname'])
        result['model'] = f"C{model_num_m.group(1)}" if model_num_m else None

    serial_m    = re.search(r'ZTP-SERIAL: (\S+)', text)
    ip_m        = re.search(r'Internet address is (\d+\.\d+\.\d+\.\d+)', text)
    version_m   = re.search(r'ZTP-VERSION: (\S+)', text)
    if serial_m:
        result['serial'] = serial_m.group(1)
    if ip_m:
        result['ip_address'] = ip_m.group(1)
    if version_m:
        result['ios_version'] = version_m.group(1)

    inventory_m = re.search(r'ZTP-INVENTORY: (.+)', text)
    if inventory_m:
        result['hw_inventory'] = inventory_m.group(1).strip()
    else:
        inv_items = []
        for match in re.finditer(r'ZTP-INV-ITEM-\d+: (.+)', text):
            try:
                inv_items.append(json.loads(match.group(1).strip()))
            except Exception:
                pass
        if inv_items:
            result['hw_inventory'] = json.dumps(inv_items)

    return result


def _server_post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f'{SERVER_URL}{path}', data=data,
        headers={'Content-Type': 'application/json'}, method='POST'
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


def _server_get_devices():
    with urllib.request.urlopen(f'{SERVER_URL}/api/devices', timeout=5) as resp:
        return json.loads(resp.read().decode())


def _server_get_all_devices():
    """Fetch ALL device rows including archived ones (used by the poller to
    prevent re-registering a hostname from a stale portlog session)."""
    with urllib.request.urlopen(f'{SERVER_URL}/api/devices/all', timeout=5) as resp:
        return json.loads(resp.read().decode())


def _server_get_failed_devices():
    with urllib.request.urlopen(f'{SERVER_URL}/api/devices/failed', timeout=5) as resp:
        return json.loads(resp.read().decode())


def device_exists(serial, hostname):
    """Returns True if this serial exists (fallback to hostname for UNKNOWN serials) in ALL devices list."""
    devices = _server_get_all_devices()
    if serial and serial != "UNKNOWN":
        return any(d.get('serial') == serial for d in devices)
    return any(d.get('hostname') == hostname for d in devices)


def register_device(device):
    return _server_post('/api/devices', device)


def post_live_session(port_id, port_label, progress, status, clear=False):
    """Update the live-session panel in the UI for this port."""
    try:
        _server_post('/api/live-session', {
            'port_id':    port_id,
            'port_label': port_label,
            'progress':   progress,
            'status':     status,
            'clear':      clear,
        })
    except Exception as e:
        print(f"[opengear] live-session update failed for {port_id}: {e}")


# Persistent state: tracks which serial was last registered per port.
# Survives poller restarts so stale portlog data doesn't re-register.
# Format: { "ports-7": {"serial": "DEMO...", "hostname": "9410-ZTP-105"}, ... }
_port_state = {}
_recorded_failures = set()   # (port_id, key) for failures — session-only


def _load_state():
    global _port_state
    _port_state = load_state(_STATE_FILE)


def _save_state():
    try:
        save_state(_STATE_FILE, _port_state)
    except Exception as e:
        print(f"[opengear] Warning: could not save state: {e}")


def poll():
    ports = get_ports()
    for port in ports:
        port_id    = port['id']
        port_label = port.get('label') or port_id

        if port.get('logging_level') in (None, 'disabled'):
            enable_port_logging(port_id)

        try:
            lines = get_portlog(port_id)
        except Exception as e:
            print(f"[opengear] Skipping {port_id}: {e}")
            continue

        if not lines:
            continue

        if DEBUG:
            print(f"[opengear] {port_id}: {len(lines)} log lines. First 3 raw:")
            for ln in lines[:3]:
                print(f"  {repr(ln)}")

        # Extract just the character stream (data) from the raw log lines
        # This removes the "RXDATA:" prefixes and joins the buffer so string searching
        # is immune to OpenGear line-wrapping or terminal-prefix noise.
        rxdata_buffer = []
        for line in lines:
            m = re.search(r'RXDATA:\s*(.*)', line)
            if m:
                rxdata_buffer.append(m.group(1))
        text_data = '\n'.join(rxdata_buffer)

        prev = _port_state.setdefault(port_id, {})
        info = parse_ztp_output(lines)

        # ── Generic Idle Tracker ──
        import hashlib
        # We hash the data stream, not the raw lines (which have timestamps).
        # This ensures we only detect actual switch activity, not time passing!
        last_stream = text_data[-50:]
        current_hash = hashlib.md5(last_stream.encode('utf-8')).hexdigest()
        activity = prev.get('activity', {'hash': None, 'idle_cycles': 10})
        
        if activity['hash'] is None:
            activity['hash'] = current_hash
            is_scrolling = False
        else:
            is_scrolling = (current_hash != activity['hash'])
        
        if is_scrolling:
            activity['hash'] = current_hash
            activity['idle_cycles'] = 0
        else:
            activity['idle_cycles'] += 1
            
        prev['activity'] = activity
        _save_state()

        # ── Pending Upgrade: Robust Registration Check ──
        if prev.get('pending'):
            # Slice the buffer to only look AFTER the 'Upgrade triggered' event.
            # This is critical to ignore manual pnpa resets or old boot logs.
            check_slice = text_data
            trigger_match = list(re.finditer(r'Upgrade triggered', text_data))
            if trigger_match:
                check_slice = text_data[trigger_match[-1].end():]

            # Use broad regex patterns for success indicators.
            # Opengear often wraps these across lines (e.g. "SYS-5-RESTAR\nT: ...").
            # The 'text_data' join handles this reasonably, but regex is safer.
            success_patterns = [
                r'Press RETURN to get started',
                r'Script execution success',
                r'SYS-5-RESTART',
                r'SYS-5-CONFIG_I',
                r'SMART_LIC-6-AGENT_READY',
                r'SMART_LIC-6-UPGRADE'
            ]
            
            is_booted = any(re.search(pat, check_slice, re.MULTILINE) for pat in success_patterns)
            
            if is_booted:
                device = prev['pending']
                print(f"[opengear] {port_id}: upgrade boot confirmed, registering {device.get('hostname')}")
                # Clear pending first to prevent double-registration in edge cases
                del prev['pending']
                result = register_device(device)
                print(f"[opengear] Registered id={result.get('id')}: {device}")
                # Save the final state so we don't re-register from this stale buffer
                _port_state[port_id] = {'serial': device.get('serial'), 'hostname': device.get('hostname'), 'activity': activity}
                _save_state()
                post_live_session(port_id, port_label, 'Upgrade complete', 'staged', clear=True)
            else:
                cl = _last_console_line(lines)
                post_live_session(port_id, port_label, cl or 'Rebooting for upgrade...', 'upgrading')
            continue

        if not info:
            # No ZTP session detected. Stream generic console if actively scrolling.
            if prev.get('serial') and device_exists(prev['serial'], prev.get('hostname')):
                if is_scrolling:
                    post_live_session(port_id, port_label, '', 'staged', clear=True)
            else:
                if is_scrolling or activity['idle_cycles'] < 10:
                    cl = _last_console_line(lines)
                    post_live_session(port_id, port_label, cl or 'Booting / Processing...', 'provisioning')
                elif activity['idle_cycles'] == 10:
                    print(f"[opengear] {port_id}: session idle/cleared")
                    # Clear state except activity tracking
                    _port_state[port_id] = {'activity': activity}
                    _save_state()
                    post_live_session(port_id, port_label, '', '', clear=True)
            continue

        status   = info.get('status', 'provisioning')
        hostname = info.get('hostname')
        # During active ZTP, show ZTP-PROGRESS messages (more informative).
        # When rebooting or between sessions, show the raw console line.
        if status == 'provisioning':
            progress = info.get('console_line') or info.get('progress', '')
        else:
            progress = info.get('progress', '')

        if status == 'failed':
            failure = info.get('failure', 'unknown error')
            serial = info.get('serial')
            fail_key = (port_id, serial or 'failed')

            # Store failure in DB (not as live session) — only once per session
            if fail_key not in _recorded_failures:
                try:
                    existing = _server_get_failed_devices()
                    already = any(
                        (serial and d.get('serial') == serial) or
                        (d.get('port_label') == port_label and d.get('failure_reason') == failure)
                        for d in existing
                    )
                except Exception:
                    already = False

                if not already:
                    device = {
                        'serial': serial,
                        'model': info.get('model'),
                        'hostname': info.get('hostname'),
                        'ip_address': info.get('ip_address'),
                        'port_label': port_label,
                        'status': 'failed',
                        'failure_reason': failure,
                    }
                    print(f"[opengear] ZTP FAILED on {port_id} ({port_label}): {failure}")
                    register_device(device)
                _recorded_failures.add(fail_key)
            continue

        serial = info.get('serial')

        # If this port was manually deleted from the DB, the server sets
        # 'suppressed' + 'suppressed_at' (UTC ISO timestamp) to block re-registration
        # from the stale portlog session. Suppression lifts when the most recent
        # ZTP-SERIAL: or Zero Touch Provisioning line in the portlog has a timestamp
        # AFTER suppressed_at — meaning a new ZTP session started after the deletion.
        # Both timestamps are parsed as timezone-aware datetimes to handle the case
        # where the OpenGear portlog uses a local offset (e.g. -07:00) and suppressed_at
        # is stored in UTC (+00:00). String comparison would give wrong results here.
        if prev.get('suppressed'):
            suppressed_at_str = prev.get('suppressed_at', '')
            latest_ztp_ts = None
            for line in reversed(lines):
                if 'ZTP-SERIAL:' in line or 'Zero Touch Provisioning' in line:
                    ts_m = re.match(r'(\S+)', line)
                    if ts_m:
                        latest_ztp_ts = ts_m.group(1)
                        break
            new_session = False
            if latest_ztp_ts and suppressed_at_str:
                try:
                    new_session = (datetime.datetime.fromisoformat(latest_ztp_ts) >
                                   datetime.datetime.fromisoformat(suppressed_at_str))
                except ValueError:
                    pass  # Unparseable timestamp — stay suppressed
            if new_session:
                # New ZTP session started after deletion — lift suppression
                prev.pop('suppressed', None)
                prev.pop('suppressed_at', None)
                prev.pop('suppressed_ztp_count', None)
                _save_state()
                print(f"[opengear] {port_id}: New ZTP session (ts={latest_ztp_ts}) after deletion "
                      f"(suppressed_at={suppressed_at_str}), lifting suppression")
            else:
                # Same session as when device was deleted — stay suppressed
                post_live_session(port_id, port_label, '', status, clear=True)
                continue

        # Once a device is fully registered ('staged') for this port, skip
        # re-registration as long as it still exists in the DB.
        if prev.get('serial') and prev['serial'] == serial and status == 'staged' and not prev.get('pending') and device_exists(serial, hostname):
            # Already handled this ZTP success — clear card.
            post_live_session(port_id, port_label, progress, status, clear=True)
            continue
        elif serial and not prev.get('pending') and device_exists(serial, hostname):
            # First time seeing this device in the DB — record it and clear card.
            _port_state[port_id] = {'serial': serial, 'hostname': hostname}
            _save_state()
            post_live_session(port_id, port_label, progress, status, clear=True)
            continue
        elif not serial and not prev.get('pending') and device_exists(None, hostname):
            # Serial absent (portlog circular buffer rotated it off) but a device
            # with this hostname is already in the DB — do not register again.
            _port_state[port_id] = {'serial': serial, 'hostname': hostname}
            _save_state()
            post_live_session(port_id, port_label, progress, status, clear=True)
            continue

        # Push a live-session update so the UI panel stays current
        post_live_session(port_id, port_label, progress, status)

        # Only register once ZTP script has fully completed ('staged').
        # If an upgrade was triggered, stash the device data in _port_state
        # as 'pending' — we'll register once we see a successful boot prompt.
        if not hostname or status == 'provisioning':
            continue

        if status == 'upgrading':
            # Save device data for later — don't register to DB yet
            device = {k: v for k, v in info.items()
                      if k in ('hostname', 'model', 'serial', 'ip_address',
                                'ios_version', 'hw_inventory')}
            if not prev.get('pending'):
                print(f"[opengear] {port_id}: upgrade triggered for {hostname}, saving data pending boot confirmation")
                _port_state[port_id] = {'serial': serial, 'hostname': hostname, 'pending': device}
                _save_state()
            continue

        # status == 'staged' — register immediately
        device = {k: v for k, v in info.items()
                  if k in ('hostname', 'model', 'serial', 'ip_address',
                            'ios_version', 'hw_inventory')}

        print(f"[opengear] ZTP device found on {port_id} ({port_label}): {hostname}")
        result = register_device(device)
        print(f"[opengear] Registered id={result.get('id')}: {device}")

        # Persist so we won't re-register this serial on restart
        _port_state[port_id] = {'serial': serial, 'hostname': hostname}
        _save_state()

        # Device is now in the DB; clear the live-session card
        post_live_session(port_id, port_label, progress, status, clear=True)


def main():
    if not OPENGEAR_USER or not OPENGEAR_PASSWORD:
        raise SystemExit("Set OPENGEAR_USER and OPENGEAR_PASSWORD environment variables.")

    _load_state()
    print(f"[opengear] Starting poller — base URL: {_base_url()}, interval={POLL_INTERVAL}s")
    print(f"[opengear] Loaded state: {len(_port_state)} ports tracked")
    print(f"[opengear] Authenticating as '{OPENGEAR_USER}'...")

    logged_in = False
    while True:
        try:
            if not logged_in:
                login()
                logged_in = True
            _load_state()  # Reload from disk each cycle to pick up server-side changes (e.g. suppressed flags)
            poll()
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print("[opengear] Session expired, re-logging in...")
                logged_in = False
                _cookies.clear()
            else:
                print(f"[opengear] HTTP {e.code}: {e}")
        except Exception as e:
            print(f"[opengear] Error: {e}")
            logged_in = False
            _cookies.clear()

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()
