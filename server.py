import json
import os
import datetime
import sqlite3
import subprocess
import tempfile
import threading
import queue
import time
import uuid
import csv
import re
from collections import Counter
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from lookup import get_lookup_source
from state_io import load_state, save_state
from itsm_push import push_device_async
import logging

logger = logging.getLogger(__name__)


def _extract_model_digits(pid: str) -> str:
    """Return first 4-digit sequence from a Cisco PID. C9410R -> '9410', C9300X-48HX -> '9300'."""
    m = re.search(r'\d{4}', pid)
    return m.group(0) if m else pid


def _build_hostname(building: str, room: str, pid: str, role: str) -> str:
    """Build hostname in the form BUILDING-ROOM-MODELDIGITS-ROLE (all uppercase)."""
    parts = [building.upper(), room.upper(), _extract_model_digits(pid), role.upper()]
    return '-'.join(p for p in parts if p)


def _normalize_module_config(hw_inventory_json) -> str:
    """Derive a normalized module config string from hw_inventory JSON.

    Used to match against the Module column in model-loc.csv.
    Returns:
      "(N) {pid}"  — N line cards with that PID (chassis like 9410)
      "{pid}"      — a network module PID (access switch like 9300)
      ""           — no expansion modules
    """
    if not hw_inventory_json:
        return ''
    try:
        items = hw_inventory_json if isinstance(hw_inventory_json, list) else json.loads(hw_inventory_json)
    except (json.JSONDecodeError, TypeError):
        return ''
    if not items:
        return ''

    lc_items = [i for i in items if 'LC-' in (i.get('pid') or '')]
    if lc_items:
        counts = Counter(i['pid'] for i in lc_items)
        pid, count = counts.most_common(1)[0]
        return f'({count}) {pid}'

    nm_items = [i for i in items if 'NM-' in (i.get('pid') or '')]
    if nm_items:
        return nm_items[0]['pid']

    return ''


class SlotAssigner:
    """Assigns the first unoccupied installation slot for a (pid, module_config) pair.

    Reads model-loc.csv (hot-reloads on mtime change). Each CSV row is one planned
    installation slot. Multiple rows with the same (pid, building, room, module) mean
    multiple units of that spec going to the same room.

    Claim check: count devices already in DB at (building, room, module) vs. plan count.
    The DB query does not filter by PID — the CSV grouping already scopes to the right type.
    """

    def __init__(self, path: str):
        self._path = path
        self._slots: list = []
        self._mtime: float | None = None

    def _load(self):
        try:
            mtime = os.path.getmtime(self._path)
        except OSError:
            return
        if mtime == self._mtime:
            return
        try:
            with open(self._path, newline='', encoding='utf-8') as f:
                slots = []
                for row in csv.DictReader(f):
                    pid = row.get('PID', '').strip()
                    if not pid:
                        continue
                    slots.append({
                        'pid':      pid,
                        'building': row.get('Bldg', '').strip(),
                        'room':     row.get('Rm', '').strip(),
                        'module':   row.get('Module', '').strip(),
                        'role':     row.get('Role', '').strip(),
                    })
            self._slots = slots
            self._mtime = mtime
            logger.info('slot-assigner: loaded %d slots from %s', len(slots), self._path)
        except Exception as exc:
            logger.warning('slot-assigner: failed to load %s: %s', self._path, exc)

    def assign(self, pid: str, module_config: str, conn) -> dict | None:
        """Return first unclaimed slot dict {building, room, module, role} or None."""
        self._load()

        plan_counts: Counter = Counter()
        slot_keys: list = []
        seen: set = set()
        for slot in self._slots:
            if slot['pid'] != pid or slot['module'] != module_config:
                continue
            key = (slot['building'], slot['room'], slot['module'], slot['role'])
            plan_counts[key] += 1
            if key not in seen:
                slot_keys.append(key)
                seen.add(key)

        for key in slot_keys:
            building, room, module, role = key
            row = conn.execute(
                'SELECT COUNT(*) FROM devices WHERE building=? AND room=? AND module=?',
                (building, room, module),
            ).fetchone()
            taken = row[0] if row else 0
            if taken < plan_counts[key]:
                return {'building': building, 'room': room, 'module': module, 'role': role}

        return None


app = Flask(__name__)

LOOKUP_SOURCE = get_lookup_source()

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get('DB_PATH', os.path.join(_APP_DIR, 'devices.db'))
STATIC = os.path.join(_APP_DIR, 'static')
POLLER_STATE = os.environ.get('POLLER_STATE_PATH', os.path.join(_APP_DIR, '.poller_state.json'))
_LOC_CSV = os.environ.get('SLOT_LOC_CSV_PATH', os.path.join(_APP_DIR, 'model-loc.csv'))
SLOT_ASSIGNER = SlotAssigner(_LOC_CSV)
# ── SSE broadcast ────────────────────────────────────────────────────────────
_sse_clients = []
_sse_lock = threading.Lock()


def notify_clients():
    """Wake all connected SSE subscribers."""
    with _sse_lock:
        for q in list(_sse_clients):
            try:
                q.put_nowait('update')
            except queue.Full:
                pass


# ── Live provisioning sessions (in-memory, poller POSTs updates) ─────────────
# { port_id: { port_label, progress, status, updated_at } }
_live_sessions = {}
_sessions_lock = threading.Lock()
SESSION_TTL = 600  # seconds — sessions older than this are pruned


def _prune_sessions():
    cutoff = time.time() - SESSION_TTL
    with _sessions_lock:
        stale = [k for k, v in _live_sessions.items() if v['updated_at'] < cutoff]
        for k in stale:
            del _live_sessions[k]


# ── Database ─────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


DEVICE_COLUMNS = [
    'id', 'hostname', 'model', 'serial', 'ip_address',
    'building', 'floor', 'room', 'module', 'asset_tag', 'notes',
    'ios_version', 'hw_inventory', 'provisioned_at', 'updated_at',
    'archived', 'status', 'failure_reason', 'port_label',
]
DEVICE_SELECT = ', '.join(DEVICE_COLUMNS)


def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS devices (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                hostname      TEXT,
                model         TEXT,
                serial        TEXT,
                ip_address    TEXT,
                building      TEXT,
                floor         TEXT,
                room          TEXT,
                asset_tag     TEXT,
                notes         TEXT,
                ios_version   TEXT,
                hw_inventory  TEXT,
                provisioned_at TEXT,
                updated_at    TEXT
            )
        ''')


def migrate_db():
    """Add any columns that were introduced after initial table creation."""
    # SQLite disallows bound parameters for DDL identifiers, so the full
    # statement is hardcoded per column — no runtime string interpolation.
    migrations = [
        ('notes',          'ALTER TABLE devices ADD COLUMN notes TEXT'),
        ('ios_version',    'ALTER TABLE devices ADD COLUMN ios_version TEXT'),
        ('hw_inventory',   'ALTER TABLE devices ADD COLUMN hw_inventory TEXT'),
        ('archived',       'ALTER TABLE devices ADD COLUMN archived INTEGER DEFAULT 0'),
        ('status',         'ALTER TABLE devices ADD COLUMN status TEXT'),
        ('failure_reason', 'ALTER TABLE devices ADD COLUMN failure_reason TEXT'),
        ('port_label',     'ALTER TABLE devices ADD COLUMN port_label TEXT'),
        ('module',         'ALTER TABLE devices ADD COLUMN module TEXT'),
    ]
    with get_db() as conn:
        existing = {row[1] for row in conn.execute('PRAGMA table_info(devices)')}
        for col, sql in migrations:
            if col not in existing:
                conn.execute(sql)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory(STATIC, 'index.html')


@app.route('/api/devices', methods=['GET'])
def list_devices():
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT {DEVICE_SELECT} FROM devices WHERE (status IS NULL OR status != 'failed') ORDER BY provisioned_at DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/devices/failed', methods=['GET'])
def list_failed_devices():
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT {DEVICE_SELECT} FROM devices WHERE status='failed' ORDER BY provisioned_at DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/devices/all', methods=['GET'])
def list_all_devices():
    """Internal endpoint — returns every row including archived ones.
    Used by the poller to avoid re-registering soft-deleted hostnames."""
    with get_db() as conn:
        rows = conn.execute(f'SELECT {DEVICE_SELECT} FROM devices').fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/lookup/<serial>', methods=['GET'])
def lookup_serial(serial):
    """Called by ztp.py on the switch to get its hostname.

    Returns the assigned hostname from the DB if this serial has already been registered
    (handles factory-reset / re-ZTP gracefully — switch gets correct hostname immediately).
    Returns {} for first-time boots; ztp.py falls back to {model}-ZTP-{ip_octet}.
    """
    with get_db() as conn:
        row = conn.execute(
            'SELECT hostname, building, room FROM devices '
            'WHERE UPPER(serial)=UPPER(?) AND hostname IS NOT NULL AND hostname != "" '
            'ORDER BY provisioned_at DESC LIMIT 1',
            (serial,)
        ).fetchone()
    if row:
        result = {'hostname': row['hostname']}
        if row['building']:
            result['building'] = row['building']
        if row['room']:
            result['room'] = row['room']
        return jsonify(result)
    return jsonify({})


@app.route('/api/devices', methods=['POST'])
def create_device():
    d = request.get_json(force=True)
    serial = d.get('serial')
    slot_assigned = False

    if serial and serial != 'UNKNOWN':
        match = LOOKUP_SOURCE.find_by_serial(serial)
        pid = match.get('pid') if match else None
        if pid:
            module_config = _normalize_module_config(d.get('hw_inventory'))
            with get_db() as conn:
                slot = SLOT_ASSIGNER.assign(pid, module_config, conn)
            if slot:
                d['building'] = slot['building']
                d['room']     = slot['room']
                d['module']   = slot['module']
                d['hostname'] = _build_hostname(slot['building'], slot['room'], pid, slot['role'])
                slot_assigned = True
            else:
                logger.warning(
                    'create_device: no slot for pid=%s module_config=%r serial=%s',
                    pid, module_config, serial,
                )

    hw_inv = d.get('hw_inventory')
    if isinstance(hw_inv, (list, dict)):
        hw_inv = json.dumps(hw_inv)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with get_db() as conn:
        cur = conn.execute(
            '''INSERT INTO devices
               (hostname, model, serial, ip_address,
                building, floor, room, module, asset_tag,
                notes, ios_version, hw_inventory,
                status, failure_reason, port_label,
                provisioned_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (d.get('hostname'), d.get('model'), d.get('serial'), d.get('ip_address'),
             d.get('building'), d.get('floor'), d.get('room'), d.get('module'), d.get('asset_tag'),
             d.get('notes'), d.get('ios_version'), hw_inv,
             d.get('status'), d.get('failure_reason'), d.get('port_label'),
             now, now)
        )
        device_id = cur.lastrowid

    if slot_assigned and d.get('ip_address'):
        _trigger_hostname_ansible(device_id, d['hostname'], d['ip_address'])

    with get_db() as conn:
        row = conn.execute(f'SELECT {DEVICE_SELECT} FROM devices WHERE id=?', (device_id,)).fetchone()
    if row:
        push_device_async(dict(row))

    notify_clients()
    return jsonify({'id': device_id}), 201


@app.route('/api/devices/<int:did>', methods=['PUT'])
def update_device(did):
    d = request.get_json(force=True)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    allowed = ['hostname', 'model', 'serial', 'ip_address',
               'building', 'floor', 'room', 'module', 'asset_tag',
               'notes', 'ios_version', 'hw_inventory',
               'status', 'failure_reason', 'port_label']
    pairs = [(f, d[f]) for f in allowed if f in d]
    if not pairs:
        return jsonify({'error': 'no fields provided'}), 400
    set_clause = ', '.join(f'{f}=?' for f, _ in pairs) + ', updated_at=?'
    values = [v for _, v in pairs] + [now, did]
    with get_db() as conn:
        conn.execute(f'UPDATE devices SET {set_clause} WHERE id=?', values)
        row = conn.execute(f'SELECT {DEVICE_SELECT} FROM devices WHERE id=?', (did,)).fetchone()
    if row:
        push_device_async(dict(row))
    notify_clients()
    return jsonify({'status': 'ok'})


@app.route('/api/devices/<int:did>', methods=['DELETE'])
def delete_device(did):
    """Permanent delete. Marks the device's port state as suppressed so the
    poller ignores the stale portlog session. The suppression is automatically
    lifted when a new ZTP session starts (factory reset), at which point the
    device is treated as brand new equipment."""
    with get_db() as conn:
        full_row = conn.execute(f'SELECT {DEVICE_SELECT} FROM devices WHERE id=?', (did,)).fetchone()
        serial = full_row['serial'] if full_row else None
        conn.execute('DELETE FROM devices WHERE id=?', (did,))
    # Push soft-delete to the optional ITSM webhook before local state is gone.
    # Downstream transforms can interpret status='deleted' as a retirement flag.
    if full_row:
        payload = dict(full_row)
        payload['status'] = 'deleted'
        payload['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        push_device_async(payload)
    # Mark this serial as suppressed in poller state. The serial/hostname are
    # retained so the poller can match them; 'suppressed' blocks re-registration
    # until a new ZTP session begins.
    if serial:
        try:
            state = load_state(POLLER_STATE)
            for port_data in state.values():
                if port_data.get('serial') == serial:
                    port_data.pop('pending', None)
                    port_data.pop('suppressed_hash', None)
                    port_data.pop('suppressed_ztp_count', None)
                    port_data.pop('ztp_session_count', None)
                    port_data['suppressed'] = True
                    port_data['suppressed_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            save_state(POLLER_STATE, state)
        except OSError:
            pass  # State file missing or unwritable — poller will self-correct
    notify_clients()
    return jsonify({'status': 'ok'})


# ── Live provisioning session updates (posted by opengear_poller) ─────────────
@app.route('/api/live-session', methods=['POST'])
def update_live_session():
    d = request.get_json(force=True)
    port_id = d.get('port_id')
    if not port_id:
        return jsonify({'error': 'port_id required'}), 400
    _prune_sessions()
    with _sessions_lock:
        if d.get('clear'):
            _live_sessions.pop(port_id, None)
        else:
            _live_sessions[port_id] = {
                'port_id':    port_id,
                'port_label': d.get('port_label', port_id),
                'progress':   d.get('progress', ''),
                'status':     d.get('status', 'provisioning'),
                'updated_at': time.time(),
            }
    notify_clients()
    return jsonify({'status': 'ok'})


@app.route('/api/live-session/<port_id>', methods=['DELETE'])
def dismiss_live_session(port_id):
    """Dismiss a live session card (e.g. a failed session that was acknowledged)."""
    with _sessions_lock:
        _live_sessions.pop(port_id, None)
    notify_clients()
    return jsonify({'status': 'ok'})


@app.route('/api/live-sessions', methods=['GET'])
def get_live_sessions():
    _prune_sessions()
    with _sessions_lock:
        sessions = sorted(_live_sessions.values(), key=lambda s: s['updated_at'], reverse=True)
    return jsonify(sessions)


# ── Server-Sent Events stream ─────────────────────────────────────────────────
@app.route('/api/stream')
def stream():
    def generate():
        q = queue.Queue(maxsize=20)
        with _sse_lock:
            _sse_clients.append(q)
        try:
            yield 'data: connected\n\n'
            while True:
                try:
                    q.get(timeout=25)
                    yield 'data: update\n\n'
                except queue.Empty:
                    yield ': heartbeat\n\n'   # keep connection alive
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


def _sync_device_fields(device_id: int, updates: dict) -> None:
    """Write a small set of allowed fields to a device row and push to ITSM.

    Used after an ansible run mutates switch state so that the registry and SN
    mirror the new values. Only columns that exist on the devices table and are
    in the caller-supplied `updates` mapping are written.
    """
    if not updates:
        return
    allowed = {'hostname', 'ip_address'}
    pairs = [(k, v) for k, v in updates.items() if k in allowed and v]
    if not pairs:
        return
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    set_clause = ', '.join(f'{k}=?' for k, _ in pairs) + ', updated_at=?'
    values = [v for _, v in pairs] + [now, device_id]
    with get_db() as conn:
        conn.execute(f'UPDATE devices SET {set_clause} WHERE id=?', values)
        row = conn.execute(f'SELECT {DEVICE_SELECT} FROM devices WHERE id=?', (device_id,)).fetchone()
    if row:
        push_device_async(dict(row))
    notify_clients()


def _trigger_hostname_ansible(device_id: int, hostname: str, ip_address: str):
    """Fire-and-forget Ansible run to push the correct hostname to the switch.

    Uses configure_device.yml with extra_vars={hostname: ...}. The run is stored
    in _ansible_runs so it appears in the UI's Ansible run log.
    Skips silently if configure_device.yml is missing (e.g. Ansible not configured).
    """
    playbook = os.path.join(ANSIBLE_PLAYBOOKS_DIR, 'configure_device.yml')
    if not os.path.isfile(playbook):
        logger.warning('_trigger_hostname_ansible: configure_device.yml not found, skipping')
        return

    run_id = str(uuid.uuid4())
    run = {
        'run_id':       run_id,
        'hostname':     hostname,
        'ip':           ip_address,
        'lines':        [],
        'rc':           None,
        'completed_at': None,
        'lock':         threading.Lock(),
        'event':        threading.Event(),
    }
    with _ansible_runs_lock:
        _ansible_runs[run_id] = run

    def execute():
        try:
            cmd = [
                'ansible-playbook',
                '-i', f'{ip_address},',
                '--extra-vars', json.dumps({'hostname': hostname}),
                playbook,
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=ANSIBLE_DIR,
            )
            for line in proc.stdout:
                with run['lock']:
                    run['lines'].append(line.rstrip())
                run['event'].set()
            proc.wait()
            with run['lock']:
                run['rc'] = proc.returncode
                run['completed_at'] = time.time()
            run['event'].set()
            if proc.returncode == 0:
                logger.info('_trigger_hostname_ansible: set hostname=%s on %s', hostname, ip_address)
            else:
                logger.warning('_trigger_hostname_ansible: rc=%d hostname=%s ip=%s',
                               proc.returncode, hostname, ip_address)
        except Exception as exc:
            with run['lock']:
                run['lines'].append(f'ERROR: {exc}')
                run['rc'] = -1
                run['completed_at'] = time.time()
            run['event'].set()
            logger.warning('_trigger_hostname_ansible: exception for %s: %s', hostname, exc)

    threading.Thread(target=execute, daemon=True).start()
    logger.info('_trigger_hostname_ansible: run_id=%s hostname=%s ip=%s', run_id, hostname, ip_address)


# ── Ansible integration ───────────────────────────────────────────────────────
# Playbooks live in /opt/ansible/playbooks/. Runs are executed as subprocesses
# from the /opt/ansible/ working directory so that ansible.cfg (vault, timeouts,
# host_key_checking=false) is picked up automatically.
#
# Each run gets a UUID. Output lines accumulate in _ansible_runs[run_id]['lines'].
# The SSE stream endpoint fans them out to the browser in real time.
# Success/failure is determined by the subprocess return code (0 = success) and
# is also parseable from the PLAY RECAP section in the output.

ANSIBLE_DIR = '/opt/ansible'
ANSIBLE_PLAYBOOKS_DIR = os.path.join(ANSIBLE_DIR, 'playbooks')

# { run_id: { hostname, ip, lines, rc, completed_at, lock, event } }
_ansible_runs: dict = {}
_ansible_runs_lock = threading.Lock()
ANSIBLE_RUN_TTL = 3600  # prune completed runs after 1 hour


def _prune_ansible_runs():
    cutoff = time.time() - ANSIBLE_RUN_TTL
    with _ansible_runs_lock:
        stale = [k for k, v in _ansible_runs.items()
                 if v['rc'] is not None and v.get('completed_at', 0) < cutoff]
        for k in stale:
            del _ansible_runs[k]


@app.route('/api/devices/export.csv', methods=['GET'])
def export_devices_csv():
    """Download all non-archived devices as a CSV file."""
    columns = [
        'hostname', 'serial', 'model', 'ip_address', 'building', 'floor', 'room',
        'module', 'ios_version', 'asset_tag', 'notes',
        'status', 'port_label', 'provisioned_at', 'updated_at',
    ]
    with get_db() as db:
        rows = db.execute(
            f'SELECT {", ".join(columns)} FROM devices WHERE archived=0 ORDER BY hostname'
        ).fetchall()

    def generate():
        buf = __import__('io').StringIO()
        writer = csv.writer(buf)
        writer.writerow(columns)
        yield buf.getvalue()
        for row in rows:
            buf = __import__('io').StringIO()
            writer = csv.writer(buf)
            writer.writerow(list(row))
            yield buf.getvalue()

    return Response(
        generate(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename="ztp_devices.csv"'},
    )


@app.route('/api/ansible/playbooks', methods=['GET'])
def list_ansible_playbooks():
    """List available .yml playbooks in /opt/ansible/playbooks/."""
    try:
        files = sorted(
            f for f in os.listdir(ANSIBLE_PLAYBOOKS_DIR)
            if f.endswith('.yml') and os.path.isfile(os.path.join(ANSIBLE_PLAYBOOKS_DIR, f))
        )
        return jsonify(files)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@app.route('/api/ansible/playbooks/<name>', methods=['GET'])
def get_ansible_playbook(name):
    """Return the raw YAML content of a named playbook."""
    if '/' in name or name.startswith('.'):
        return jsonify({'error': 'invalid name'}), 400
    path = os.path.join(ANSIBLE_PLAYBOOKS_DIR, name)
    if not os.path.isfile(path):
        return jsonify({'error': 'not found'}), 404
    with open(path, encoding='utf-8') as f:
        return f.read(), 200, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/api/ansible/run', methods=['POST'])
def run_ansible_playbook():
    """Start an ansible-playbook run against a single device.

    Request body: { "device_id": <int>, "playbook": "<yaml string>" }
    Returns:      { "run_id": "<uuid>" }

    The playbook is written to a temp file; a one-host inventory is generated
    from the device's ip_address. Both are deleted after the run completes.
    """
    d = request.get_json(force=True)
    device_id = d.get('device_id')
    playbook_content = d.get('playbook', '').strip()
    extra_vars = d.get('vars')  # optional dict; passed as --extra-vars if present

    if not device_id or not playbook_content:
        return jsonify({'error': 'device_id and playbook are required'}), 400

    with get_db() as conn:
        row = conn.execute(
            'SELECT ip_address, hostname FROM devices WHERE id=?', (device_id,)
        ).fetchone()
    if not row:
        return jsonify({'error': 'device not found'}), 404

    ip_address = row['ip_address']
    hostname = row['hostname']
    run_id = str(uuid.uuid4())

    _prune_ansible_runs()
    run = {
        'run_id':   run_id,
        'hostname': hostname,
        'ip':       ip_address,
        'lines':    [],      # all stdout/stderr lines captured so far
        'rc':       None,    # None while running; int when done
        'completed_at': None,
        'lock':     threading.Lock(),
        'event':    threading.Event(),
    }
    with _ansible_runs_lock:
        _ansible_runs[run_id] = run

    def execute():
        tmp_playbook = None
        try:
            # Write to playbooks/ dir (not /tmp) so that ansible picks up
            # group_vars/ from the same directory as a normal playbook would.
            with tempfile.NamedTemporaryFile(
                    mode='w', suffix='.yml', dir=ANSIBLE_PLAYBOOKS_DIR,
                    delete=False, encoding='utf-8') as pf:
                pf.write(playbook_content)
                tmp_playbook = pf.name

            # Comma suffix tells Ansible to treat the argument as an inline
            # inventory (one host) rather than a file path.
            cmd = ['ansible-playbook', '-i', f'{ip_address},', tmp_playbook]
            if extra_vars and isinstance(extra_vars, dict):
                cmd += ['--extra-vars', json.dumps(extra_vars)]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=ANSIBLE_DIR,
            )
            for line in proc.stdout:
                with run['lock']:
                    run['lines'].append(line.rstrip())
                run['event'].set()
            proc.wait()
            with run['lock']:
                run['rc'] = proc.returncode
                run['completed_at'] = time.time()
            run['event'].set()

            # On success, sync any ansible-mutated DB-tracked fields so that
            # ITSM integrations (and the UI) reflect the switch's new state. Only
            # fields that are both in the DB schema AND settable by the
            # playbook are propagated.
            if proc.returncode == 0 and isinstance(extra_vars, dict):
                ansible_to_db = {'hostname': 'hostname', 'mgmt_ip': 'ip_address'}
                db_updates = {
                    col: extra_vars[avar]
                    for avar, col in ansible_to_db.items()
                    if extra_vars.get(avar)
                }
                if db_updates:
                    try:
                        _sync_device_fields(device_id, db_updates)
                    except Exception as sync_err:
                        logger.warning('post-ansible DB sync failed device=%s err=%s',
                                       device_id, sync_err)
        except Exception as exc:
            with run['lock']:
                run['lines'].append(f'ERROR: {exc}')
                run['rc'] = -1
                run['completed_at'] = time.time()
            run['event'].set()
        finally:
            if tmp_playbook:
                try:
                    os.unlink(tmp_playbook)
                except OSError:
                    pass

    threading.Thread(target=execute, daemon=True).start()
    return jsonify({'run_id': run_id})


@app.route('/api/ansible/stream/<run_id>', methods=['GET'])
def stream_ansible_run(run_id):
    """SSE stream of output for an ansible run.

    Events emitted:
      data: {"type":"start","hostname":"...","ip":"..."}
      data: {"type":"line","text":"<output line>"}     (one per line, as available)
      data: {"type":"done","rc":<int>,"success":<bool>}
    """
    with _ansible_runs_lock:
        run = _ansible_runs.get(run_id)
    if not run:
        return jsonify({'error': 'run not found'}), 404

    def generate():
        yield f'data: {json.dumps({"type":"start","hostname":run["hostname"],"ip":run["ip"]})}\n\n'
        sent = 0
        while True:
            run['event'].wait(timeout=2)
            run['event'].clear()
            with run['lock']:
                new_lines = run['lines'][sent:]
                rc = run['rc']
            for line in new_lines:
                yield f'data: {json.dumps({"type":"line","text":line})}\n\n'
            sent += len(new_lines)
            if rc is not None:
                yield f'data: {json.dumps({"type":"done","rc":rc,"success":rc == 0})}\n\n'
                break

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


if __name__ == '__main__':
    init_db()
    migrate_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
